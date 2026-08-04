"""MQTT link to the IR emitter.

We never assume a published message arrived. Every plan carries an id, the
emitter echoes it on the ack topic, and `send()` waits for it. Without that the
backend cannot tell "fired" from "lost", and it would happily tell her the TV
is on when nothing happened.

The emitter also registers a Last Will on the status topic, so `is_online`
turns false within seconds of it dropping off rather than on the next timeout.
"""

from __future__ import annotations

import asyncio
import json
import logging

from paho.mqtt import client as mqtt

from .config import settings
from .schemas import Ack, Plan

log = logging.getLogger(__name__)


class EmitterOffline(Exception):
    pass


class EmitterTimeout(Exception):
    pass


class Emitter:
    def __init__(self) -> None:
        self._client: mqtt.Client | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self.online = False

    # --- lifecycle ------------------------------------------------------

    async def connect(self) -> None:
        if settings.offline:
            self.online = True
            return

        self._loop = asyncio.get_running_loop()
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if settings.mqtt_username:
            client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
        if settings.mqtt_tls:
            client.tls_set()  # system CA bundle; hosted brokers use real certs
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.reconnect_delay_set(min_delay=1, max_delay=30)

        # connect_async never raises on an unreachable broker -- it hands the
        # retry loop to paho. That matters: the service must come up and start
        # answering, telling her the emitter is offline, rather than crash-
        # looping because the broker happened to be down at deploy time.
        client.connect_async(settings.mqtt_host, settings.mqtt_port, keepalive=30)
        client.loop_start()
        self._client = client

    async def close(self) -> None:
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()

    # --- callbacks (paho thread) ---------------------------------------

    def _on_connect(self, client, _userdata, _flags, _rc, _props=None) -> None:
        client.subscribe([(settings.topic_ack, 1), (settings.topic_status, 1)])
        log.info("mqtt connected to %s:%s", settings.mqtt_host, settings.mqtt_port)

    def _on_disconnect(self, _client, _userdata, *args) -> None:
        # Our own link to the broker is down, so we cannot know the emitter's
        # state. Assume offline: she gets told the box is unreachable instead
        # of a confirmation for a command that went nowhere.
        self.online = False
        log.warning("mqtt disconnected")

    def _on_message(self, _client, _userdata, msg) -> None:
        if msg.topic == settings.topic_status:
            self.online = msg.payload.decode().strip() == "online"
            return

        try:
            ack = Ack.model_validate_json(msg.payload)
        except Exception:
            return

        future = self._pending.pop(ack.id, None)
        if future and self._loop and not future.done():
            self._loop.call_soon_threadsafe(future.set_result, ack)

    # --- sending --------------------------------------------------------

    async def send(self, plan: Plan) -> Ack:
        if settings.offline:
            log.info("offline: would publish %s", plan.model_dump_json())
            return Ack(id=plan.id, ok=True)

        if not self.online:
            raise EmitterOffline("emitter has not reported online")
        if self._client is None:
            raise EmitterOffline("mqtt client not connected")

        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[plan.id] = future

        self._client.publish(
            settings.topic_cmd,
            json.dumps({"id": plan.id, "steps": [s.model_dump() for s in plan.steps]}),
            qos=1,
        )

        try:
            return await asyncio.wait_for(future, timeout=settings.ack_timeout_s)
        except asyncio.TimeoutError as exc:
            self._pending.pop(plan.id, None)
            raise EmitterTimeout(f"no ack for {plan.id}") from exc


emitter = Emitter()
