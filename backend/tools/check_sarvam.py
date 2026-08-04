#!/usr/bin/env python3
"""Go/no-go on the riskiest assumption in the project.

Before any hardware exists, this answers the only question that can kill
RevGen: does Saaras actually handle *her* Malayalam? Elderly speech, regional
pronunciation, code-mixing, a television playing in the background.

    1. Record her on a phone saying real commands, one file each.
    2. Drop the files in a folder. Voice memos are fine as-is -- .m4a from an
       iPhone, .mp3 or .opus from Android, .ogg out of WhatsApp all work.
    3. python tools/check_sarvam.py recordings/

It prints the transcript and the resolved intent for each file, then an
accuracy summary. Name a file with the expected action to have it scored:

    01_tv_on__power_on.wav          -> expects power_on
    02_background_noise__unknown.wav -> expects unknown

Everything after the double underscore is the expectation.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import audio                    # noqa: E402
from app.catalog import Catalog          # noqa: E402
from app.config import settings          # noqa: E402
from app.intent import extract           # noqa: E402
from app.stt import transcribe           # noqa: E402


def expected_action(path: Path) -> str | None:
    stem = path.stem
    return stem.rsplit("__", 1)[1] if "__" in stem else None


async def main(folder: Path) -> int:
    if not settings.sarvam_api_key:
        print("SARVAM_API_KEY is not set. Put it in backend/.env")
        return 2

    catalog = Catalog.load(settings.catalog_path)
    files = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in audio.SUPPORTED_EXTENSIONS
    )
    if not files:
        print(f"no audio files in {folder}")
        print("supported: " + ", ".join(sorted(
            e.lstrip(".") for e in audio.SUPPORTED_EXTENSIONS
        )))
        return 2

    scored = correct = transcribed = 0

    for path in files:
        print(path.name)

        # The two stages are reported separately on purpose. A working
        # transcription is the more valuable of the two results, and it must
        # not be swallowed by a later failure in the intent call.
        try:
            transcript = await transcribe(path.read_bytes(), path.name)
            transcribed += 1
            print(f"  heard    {transcript!r}")
        except Exception as exc:
            print(f"  STT FAILED: {exc}\n")
            continue

        try:
            intents = await extract(transcript, catalog)
        except Exception as exc:
            print(f"  INTENT FAILED: {exc}\n")
            continue

        for i, intent in enumerate(intents):
            label = "  intent  " if i == 0 else "     +   "
            device = intent.device.value if intent.device else "-"
            steps = f" steps={intent.steps}" if intent.steps > 1 else ""
            print(f"{label} {intent.action.value}  device={device} "
                  f"conf={intent.confidence}{steps}")

        # An utterance is correct if the expected action appears anywhere in it.
        # Compound requests are normal, so scoring only the first would punish
        # the model for hearing everything she said.
        expected = expected_action(path)
        if expected:
            scored += 1
            got = {i.action.value for i in intents}
            ok = expected in got
            correct += ok
            print(f"           {'OK' if ok else f'WRONG (wanted {expected})'}")
        print()

    print("-" * 60)
    print(f"transcribed {transcribed}/{len(files)}")

    if scored:
        pct = 100 * correct / scored
        print(f"intent accuracy: {correct}/{scored}  ({pct:.0f}%)")
        print("target is 95%. Below that, try mode=transcribe instead of codemix")
        print("before changing anything else -- STT mode is the biggest single lever.")
    elif transcribed:
        print("none scored. Rename files so the expected action follows a double")
        print("underscore, e.g.  01_tv_on__power_on.m4a  ->  expects power_on")

    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("recordings")
    raise SystemExit(asyncio.run(main(target)))
