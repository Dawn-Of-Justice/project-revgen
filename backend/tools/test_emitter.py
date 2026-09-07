#!/usr/bin/env python3
"""Send a catalog button through the backend MQTT client, without STT/TTS.

Default is dry-run. --execute deliberately emits IR on the configured topic.
Run from backend so settings load backend/.env.
"""
import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.catalog import Catalog
from app.config import settings
from app.emitter import Emitter
from app.emitter_protocol import encode_command
from app.schemas import Device, Plan


async def run(args):
    catalog = Catalog.load(settings.catalog_path)
    plan = Plan(id=str(uuid.uuid4()), steps=[catalog.step(Device(args.device), args.button)])
    print(encode_command(plan, settings.topic_cmd).decode())
    if not args.execute:
        print("Dry run: no network connection or IR emission. Add --execute to send.")
        return 0
    if settings.offline:
        raise ValueError("OFFLINE=true would simulate success; disable it for this test")
    link = Emitter()
    await link.connect()
    try:
        deadline = asyncio.get_running_loop().time() + args.wait
        while not link.online and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(.1)
        ack = await link.send(plan)
        print(ack.model_dump_json())
        print("Accepted for IR execution; visually check the appliance response." if ack.ok else "Emitter rejected the command.")
        return 0 if ack.ok else 1
    finally:
        await link.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device", choices=[d.value for d in Device])
    parser.add_argument("button", help="catalog button, e.g. volume_up or channel_up")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--wait", type=float, default=15, help="seconds to wait for online status")
    try:
        sys.exit(asyncio.run(run(parser.parse_args())))
    except Exception as exc:
        print(f"Test failed: {exc}", file=sys.stderr)
        sys.exit(1)
