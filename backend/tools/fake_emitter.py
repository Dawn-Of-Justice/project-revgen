#!/usr/bin/env python3
"""Pretend to be the IR emitter, so the whole system can be tested with no hardware.

    python tools/fake_emitter.py

Subscribes to the command topic, prints each step in plain English, and
publishes an ack — exactly what firmware/emitter/emitter.ino does, minus the
infrared. It also announces itself on the status topic, so the backend reports
`emitter_online: true` and stops answering err.emitter_offline.

With this running, `send_wav.py` returns the real Malayalam confirmation. That
is the entire pipeline proven end to end: her voice in, IR instructions out,
spoken reply back. The only untested thing left is whether the physical LED
flashes.

It deliberately mirrors emitter.ino's validation rules. If this rejects a
command, the real firmware would too — which makes it a live check on the wire
contract, not just a viewer.

Reads credentials from backend/.env, so nothing sensitive goes on the command
line or into shell history.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from paho.mqtt import client as mqtt   # noqa: E402

from app.config import settings        # noqa: E402
from app.emitter_protocol import validate_steps  # noqa: E402

def describe(step: dict) -> str:
    if step.get("type") == "delay":
        return f"        wait {step['ms']}ms"
    if step.get("protocol") == "panasonic":
        return (f"        IR  panasonic  addr=0x{step['address']:X} "
                f"cmd=0x{step['command']:02X}")
    if step.get("protocol") == "nec_raw":
        return f"        IR  nec_raw    0x{step['raw']:08X}"
    return f"        ?? {step}"


def validate(steps: list) -> str | None:
    """Same checks emitter.ino::parseSteps performs. Returns an error or None."""
    return validate_steps(steps)


def on_connect(client, _u, _f, _rc, _p=None):
    client.subscribe(settings.topic_cmd, 1)
    client.publish(settings.topic_status, "online", retain=True)
    print(f"connected, listening on {settings.topic_cmd}")
    print("backend should now report emitter_online: true\n")


def on_message(client, _u, msg):
    stamp = time.strftime("%H:%M:%S")
    try:
        payload = json.loads(msg.payload)
    except json.JSONDecodeError:
        print(f"[{stamp}] unparseable payload: {msg.payload[:120]!r}")
        return

    if not isinstance(payload, dict):
        print("invalid command object")
        return
    plan_id = payload.get("id", "")
    if not isinstance(plan_id, str) or not plan_id or len(plan_id.encode()) > 47 or "\0" in plan_id:
        print("invalid command id")
        return
    steps = payload.get("steps") or []
    if not isinstance(steps, list):
        client.publish(settings.topic_ack, json.dumps({"id": plan_id, "ok": False, "error": "no steps"}))
        return
    print(f"[{stamp}] command {plan_id[:8]}  ({len(steps)} steps, "
          f"{len(msg.payload)}B of a 2048B firmware buffer)")

    error = validate(steps)
    if error:
        # The real firmware refuses the entire sequence rather than
        # half-executing it. Mirror that.
        print(f"        REJECTED: {error}")
        client.publish(settings.topic_ack,
                       json.dumps({"id": plan_id, "ok": False, "error": error}))
        return

    for step in steps:
        print(describe(step))

    client.publish(settings.topic_ack, json.dumps({"id": plan_id, "ok": True}))
    print("        acked\n")


def main() -> int:
    if not settings.mqtt_host or settings.mqtt_host == "localhost":
        print("MQTT_HOST is not set. Put it in backend/.env:")
        print("  MQTT_HOST=xxxxx.s1.eu.hivemq.cloud")
        print("  MQTT_PORT=8883")
        print("  MQTT_TLS=true")
        print("  MQTT_USERNAME=...")
        print("  MQTT_PASSWORD=...")
        return 2

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if settings.mqtt_username:
        client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
    if settings.mqtt_tls:
        client.tls_set()

    # Last Will, same as the firmware: if this dies, the backend finds out
    # immediately rather than on the next timeout.
    client.will_set(settings.topic_status, "offline", retain=True)
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"connecting to {settings.mqtt_host}:{settings.mqtt_port} ...")
    client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=30)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        client.publish(settings.topic_status, "offline", retain=True)
        client.disconnect()
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
