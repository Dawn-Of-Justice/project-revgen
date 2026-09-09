"""Bulbul v3, cached to disk.

The cache is not a cost optimisation -- it is the latency budget. Playback has
to *begin* within about 1.2s of her finishing speaking, because that is what
stops her repeating herself and toggling the TV back off. A live TTS round trip
would spend most of that budget on its own.

There are only ~15 reachable phrases, so `tools/build_tts_cache.py` generates
them all once at deploy time and this module usually just reads a file.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import wave
from pathlib import Path

import httpx

from .config import settings


class TTSError(Exception):
    pass


def cache_path(text: str) -> Path:
    # Changing the voice or format must not reuse an old (e.g. 24 kHz) clip.
    key = [text, settings.tts_model, settings.tts_speaker, settings.tts_pace,
           settings.tts_sample_rate, "ml-IN", "wav", settings.offline]
    digest = hashlib.sha256(json.dumps(key).encode("utf-8")).hexdigest()[:16]
    return settings.tts_cache_dir / f"{digest}.wav"


def _validate_wav(audio: bytes) -> None:
    """Enforce the mono PCM16 contract used by the remote's I2S playback."""
    rate = int(settings.tts_sample_rate)
    if rate not in {8000, 16000, 32000, 44100, 48000}:
        raise TTSError("TTS sample rate is unsupported by the remote amplifier")
    try:
        with wave.open(io.BytesIO(audio), "rb") as reader:
            if (reader.getnchannels(), reader.getsampwidth(), reader.getframerate()) != (1, 2, rate):
                raise TTSError("TTS audio must be mono PCM16 at the configured sample rate")
            frames = reader.getnframes()
            if frames == 0 or len(reader.readframes(frames)) != frames * 2:
                raise TTSError("TTS audio is empty or truncated")
    except (wave.Error, EOFError) as exc:
        raise TTSError("TTS returned invalid WAV audio") from exc


async def speak(text: str) -> bytes:
    """Return WAV bytes for `text`, generating and caching on a miss."""
    path = cache_path(text)
    if path.exists():
        audio = path.read_bytes()
        try:
            _validate_wav(audio)
            return audio
        except TTSError:
            pass  # Regenerate a corrupt or obsolete cache entry.

    audio = await _synthesise(text)
    _validate_wav(audio)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    return audio


async def speak_all(texts: list[str]) -> bytes:
    """Several phrases, spoken back to back, as one WAV.

    A compound request ("turn it on and turn it up") deserves a compound
    confirmation. We stitch the individual cached clips rather than synthesising
    the joined sentence, because a joined string would be a new cache key on
    every combination -- and the cache is what keeps playback inside the 1.2s
    budget that stops her repeating herself.
    """
    if not texts:
        raise TTSError("nothing to say")
    if len(texts) == 1:
        return await speak(texts[0])

    clips = [await speak(text) for text in texts]
    try:
        return _concat_wav(clips)
    except (wave.Error, EOFError):
        # Non-WAV or mismatched clips (e.g. offline placeholders). Falling back
        # to the first phrase is still sound, which is the requirement.
        return clips[0]


def _concat_wav(clips: list[bytes]) -> bytes:
    """Join WAVs that share sample rate, width and channel count."""
    out = io.BytesIO()
    writer: wave.Wave_write | None = None

    for clip in clips:
        with wave.open(io.BytesIO(clip), "rb") as reader:
            if writer is None:
                writer = wave.open(out, "wb")
                writer.setparams(reader.getparams())
            elif reader.getparams()[:3] != writer.getparams()[:3]:
                raise wave.Error("clip parameters differ")
            writer.writeframes(reader.readframes(reader.getnframes()))

    if writer is None:
        raise wave.Error("no clips")
    writer.close()
    return out.getvalue()


async def _synthesise(text: str) -> bytes:
    if settings.offline:
        out = io.BytesIO()
        with wave.open(out, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(int(settings.tts_sample_rate))
            writer.writeframes(b"\x00\x00" * (int(settings.tts_sample_rate) // 10))
        return out.getvalue()  # Valid silence for offline integration tests.

    if not settings.sarvam_api_key:
        raise TTSError("SARVAM_API_KEY is not set")

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            response = await client.post(
                f"{settings.sarvam_base}/text-to-speech",
                headers={
                    "api-subscription-key": settings.sarvam_api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "target_language_code": "ml-IN",
                    "model": settings.tts_model,
                    "speaker": settings.tts_speaker,
                    "pace": settings.tts_pace,
                    "speech_sample_rate": settings.tts_sample_rate,
                    "output_audio_codec": "wav",
                },
            )
        except httpx.RequestError as exc:
            raise TTSError(f"network error talking to Bulbul: {exc}") from exc

    if response.status_code != 200:
        raise TTSError(f"Bulbul returned {response.status_code}: {response.text[:300]}")

    audios = response.json().get("audios") or []
    if not audios:
        raise TTSError("Bulbul returned no audio")

    return base64.b64decode("".join(audios))
