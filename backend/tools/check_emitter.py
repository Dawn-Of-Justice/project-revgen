"""Check broker access and emitter status; --probe sends a zero-delay ACK test.

Run from backend. The probe emits no IR and does not operate the appliance.
"""
import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import settings
from app.emitter import Emitter
from app.schemas import DelayStep, Plan


async def check(probe):
    if settings.offline:
        raise RuntimeError("OFFLINE=true; this check requires a real broker")
    link = Emitter()
    await link.connect()
    try:
        deadline = asyncio.get_running_loop().time() + 15
        while not link.online and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(.1)
        print("Broker connection: " + ("connected" if link._client and link._client.is_connected() else "not connected"))
        print("Emitter status: " + ("online" if link.online else "not online"))
        if probe and link.online:
            ack = await link.send(Plan(id=str(uuid.uuid4()), steps=[DelayStep(ms=0)]))
            print("Zero-delay probe: " + ("ACK received" if ack.ok else f"rejected: {ack.error}"))
            return 0 if ack.ok else 1
        return 0 if link.online else 1
    finally:
        await link.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    try:
        sys.exit(asyncio.run(check(args.probe)))
    except Exception as exc:
        print(f"Check failed: {exc}", file=sys.stderr)
        sys.exit(1)
