"""Saaras v3 speech-to-text.

POST https://api.sarvam.ai/speech-to-text  (multipart)
  model=saaras:v3  mode=codemix  language_code=ml-IN

`mode=codemix` is the deliberate choice: it keeps English words in Latin script
and Malayalam in native script, so "TV ഓൺ ആക്കൂ" survives intact. That is how
she will actually speak, and it is the form the intent model reads best.

`language_code=ml-IN` is set explicitly rather than `unknown` -- it skips
language detection, which is both faster and one fewer thing to get wrong.

Input may be WAV, MP3, M4A or any other container Saaras accepts. The remote
always sends WAV; phone recordings used for testing arrive as whatever the
handset produced. `audio.identify()` works it out from the bytes.
"""

from __future__ import annotations

import httpx

from . import audio
from .config import settings


class STTError(Exception):
    pass


async def transcribe(data: bytes, filename: str = "command.wav") -> str:
    if settings.offline:
        return "__offline__"

    if not settings.sarvam_api_key:
        raise STTError("SARVAM_API_KEY is not set")

    try:
        fmt = audio.identify(data, filename)
    except audio.UnsupportedAudio as exc:
        raise STTError(str(exc)) from exc

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(
                f"{settings.sarvam_base}/speech-to-text",
                headers={"api-subscription-key": settings.sarvam_api_key},
                files={
                    "file": (audio.upload_name(fmt, filename), data, fmt.mime),
                },
                data={
                    "model": settings.stt_model,
                    "mode": settings.stt_mode,
                    "language_code": settings.stt_language,
                },
            )
        except httpx.RequestError as exc:
            raise STTError(f"network error talking to Saaras: {exc}") from exc

    if response.status_code != 200:
        raise STTError(f"Saaras returned {response.status_code}: {response.text[:300]}")

    return (response.json().get("transcript") or "").strip()
