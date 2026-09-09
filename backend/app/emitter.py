"""MQTT link to the IR emitter.

We never assume a published message arrived. Every plan carries an id, the
emitter echoes it on the ack topic, and `send()` waits for it. Without that the
backend cannot tell "accepted" from "lost". The ACK does not confirm that the
IR sequence completed or that the appliance reacted.

The emitter also registers a Last Will on the status topic. Offline detection
depends on the broker's keepalive timeout; it is not instantaneous.
"""

from __future__ import annotations

import asyncio
import logging
import json

from paho.mqtt import client as mqtt

from .config import settings
from .emitter_protocol import encode_command
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
        self.learning_handler = None

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
        self._mark_disconnected()
        if self._client:
            self._client.disconnect()
            await asyncio.to_thread(self._client.loop_stop)
            self._client = None

    def _mark_disconnected(self) -> None:
        self.online = False
        for future in self._pending.values():
            if not future.done():
                future.set_exception(EmitterOffline("mqtt link disconnected"))

    def _dispatch(self, callback, *args) -> None:
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(callback, *args)

    # --- callbacks (paho thread) ---------------------------------------

    def _on_connect(self, client, _userdata, _flags, _rc, _props=None) -> None:
        if _rc != 0:
            self._dispatch(self._mark_disconnected)
            log.warning("mqtt connection refused: %s", _rc)
            return
        client.subscribe([(settings.topic_ack, 1), (settings.topic_status, 1),
                          (settings.topic_learn, 1)])
        log.info("mqtt connected to %s:%s", settings.mqtt_host, settings.mqtt_port)

    def _on_disconnect(self, _client, _userdata, *args) -> None:
        # Our own link to the broker is down, so we cannot know the emitter's
        # state. Assume offline: she gets told the box is unreachable instead
        # of a confirmation for a command that went nowhere.
        self._dispatch(self._mark_disconnected)
        log.warning("mqtt disconnected")

    def _on_message(self, _client, _userdata, msg) -> None:
        if msg.topic == settings.topic_learn:
            if not msg.retain and len(msg.payload) <= 1536:
                self._dispatch(self._accept_learning, bytes(msg.payload))
            return
        if msg.topic == settings.topic_status:
            self._dispatch(setattr, self, "online", msg.payload == b"online")
            return

        if msg.topic != settings.topic_ack:
            return

        try:
            ack = Ack.model_validate_json(msg.payload)
        except Exception:
            return

        self._dispatch(self._accept_ack, ack)

    def _accept_learning(self, payload: bytes) -> None:
        if self.learning_handler is None or self._client is None:
            return  # Emitter retains the outbox and retries after backend startup.
        try:
            ack = self.learning_handler(payload)
        except OSError:
            log.exception("learning storage unavailable; emitter will retry")
            return  # Keep the durable outbox pending after a transient disk failure.
        except Exception as exc:
            log.warning("learning update refused: %s", type(exc).__name__)
            try:
                ident = json.loads(payload).get("id")
                if not isinstance(ident, str) or not 8 <= len(ident) <= 48:
                    return
            except (ValueError, AttributeError):
                return
            ack = {"id": ident, "ok": False, "error": "Invalid or stale mapping; edit and save again"}
        self._client.publish(settings.topic_learn_ack, json.dumps(ack), qos=1, retain=False)

    def _accept_ack(self, ack: Ack) -> None:
        # The lookup and completion run together on asyncio's thread. An ACK
        # arriving after wait_for cancelled its future must be harmless.
        future = self._pending.get(ack.id)
        if future is not None and not future.done():
            future.set_result(ack)

    # --- sending --------------------------------------------------------

    async def send(self, plan: Plan) -> Ack:
        payload = encode_command(plan, settings.topic_cmd)
        if settings.offline:
            log.info("offline: would publish %s", plan.model_dump_json())
            return Ack(id=plan.id, ok=True)

        if not self.online:
            raise EmitterOffline("emitter has not reported online")
        if self._client is None:
            raise EmitterOffline("mqtt client not connected")

        future: asyncio.Future = asyncio.get_running_loop().create_future()
        if plan.id in self._pending:
            raise ValueError("command id already awaiting acknowledgement")
        self._pending[plan.id] = future
        try:
            result = self._client.publish(settings.topic_cmd, payload, qos=1, retain=False)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise EmitterOffline(f"mqtt publish failed: {result.rc}")
            return await asyncio.wait_for(future, timeout=settings.ack_timeout_s)
        except asyncio.TimeoutError as exc:
            raise EmitterTimeout(f"no ack for {plan.id}") from exc
        finally:
            self._pending.pop(plan.id, None)
            if not future.done():
                future.cancel()


emitter = Emitter()
