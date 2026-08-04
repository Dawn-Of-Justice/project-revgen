#!/usr/bin/env python3
"""Stand in for the voice unit.

    python tools/send_wav.py recordings/tv_on.m4a
    python tools/send_wav.py recordings/tv_on.m4a https://revgen.fly.dev/command

Takes WAV, MP3, M4A or anything else Saaras reads, so you can point it straight
at a voice memo off your phone without converting first. The format is sniffed
from the file's bytes, not its extension.

Against a deployed backend, set DEVICE_TOKEN in the environment (or in
backend/.env) to match the one in `fly secrets`. Without it you get a 401.

This is the Phase 2 acceptance test: a recording from your laptop controls the
TV, with the entire intelligence layer proven and no new hardware. Once this
works, the handheld is the only remaining unknown in the system.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import audio          # noqa: E402
from app.config import settings  # noqa: E402

BACKEND = "http://localhost:8000/command"


def play(path: Path) -> None:
    for player in (["aplay", str(path)], ["afplay", str(path)]):
        try:
            subprocess.run(player, check=True, capture_output=True)
            return
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    print(f"(saved reply to {path}; no aplay/afplay found)")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    path = Path(sys.argv[1])
    url = sys.argv[2] if len(sys.argv) > 2 else BACKEND

    if not path.exists():
        print(f"no such file: {path}")
        return 2

    data = path.read_bytes()
    try:
        fmt = audio.identify(data, path.name)
    except audio.UnsupportedAudio as exc:
        print(exc)
        return 2

    headers = {}
    if settings.device_token:
        headers["X-RevGen-Token"] = settings.device_token

    print(f"sending {path.name}  [{fmt.name}, {len(data) / 1024:.0f} KB]"
          f"{'  +token' if headers else ''}")

    started = time.monotonic()
    response = httpx.post(
        url,
        files={"file": (audio.upload_name(fmt, path.name), data, fmt.mime)},
        headers=headers,
        timeout=30.0,
    )
    elapsed = int((time.monotonic() - started) * 1000)

    if response.status_code == 401:
        print("401: DEVICE_TOKEN is unset or does not match `fly secrets list`")
        return 1

    outcome = response.headers.get("X-RevGen-Outcome", "?")
    server_ms = response.headers.get("X-RevGen-Elapsed-Ms", "?")
    print(f"{response.status_code}  outcome={outcome}  server={server_ms}ms  total={elapsed}ms")

    if elapsed > 3000:
        print("  slow: budget is 3s end to end, and 1.2s to the start of playback")

    if response.headers.get("content-type", "").startswith("audio/"):
        out = Path("reply.wav")
        out.write_bytes(response.content)
        play(out)
    else:
        print(response.text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
