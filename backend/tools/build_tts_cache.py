#!/usr/bin/env python3
"""Pre-generate every confirmation phrase.

Run once at deploy time and after any edit to the phrases block in
commands.json. There are only ~15 of them, so runtime TTS cost drops to zero
and, more importantly, playback starts immediately instead of after a round
trip -- which is what keeps her from repeating herself.

    python tools/build_tts_cache.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# bulbul:v3 is capped at 30 req/min on the Starter plan -- half the default TTS
# limit. One request every 2.1s keeps a full cache rebuild under it without
# needing retry logic.
THROTTLE_S = 2.1

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.catalog import Catalog     # noqa: E402
from app.config import settings     # noqa: E402
from app.tts import cache_path, speak   # noqa: E402


async def main() -> int:
    catalog = Catalog.load(settings.catalog_path)
    phrases = catalog.all_phrases()

    built = skipped = failed = 0

    for key, template in phrases.items():
        # Templated phrases vary at runtime; the channel name is baked in, so
        # pre-render one per configured channel instead of the raw template.
        variants = (
            [catalog.phrase(key, channel=name) for name in catalog.channel_names()]
            if "{channel}" in template
            else [template]
        )

        for text in variants:
            if cache_path(text).exists():
                skipped += 1
                continue
            try:
                await speak(text)
                built += 1
                print(f"  built  {key}: {text}")
                await asyncio.sleep(THROTTLE_S)
            except Exception as exc:
                failed += 1
                print(f"  FAILED {key}: {exc}")

    print(f"\n{built} built, {skipped} already cached, {failed} failed")
    print(f"cache: {settings.tts_cache_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
