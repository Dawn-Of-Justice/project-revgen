"""Append-only record of every utterance and what came of it.

This exists because the device lives in someone else's house. When something
goes wrong the alternative to this file is debugging by phone with an elderly
person describing symptoms, which is a worse failure than any bug.

One JSON object per line: greppable, tailable, and trivially turned into the
test set that STT and intent accuracy get measured against.
"""

from __future__ import annotations

import json
import time
from typing import Any

from .config import settings


def record(**fields: Any) -> None:
    entry = {"ts": time.time(), **fields}
    try:
        settings.log_path.parent.mkdir(parents=True, exist_ok=True)
        with settings.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        # Logging must never take the system down with it.
        pass
