"""Playback format and persistent-cache regression coverage."""

import base64
import hashlib
import io
import wave

import httpx
import pytest

from app import tts
from app.config import settings


def wav(rate=32000, channels=1, width=2):
    out = io.BytesIO()
    with wave.open(out, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(width)
        writer.setframerate(rate)
        writer.writeframes(b"\x00" * (160 * channels * width))
    return out.getvalue()


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "tts_sample_rate", "32000")
    monkeypatch.setattr(settings, "offline", False)
    monkeypatch.setattr(settings, "sarvam_api_key", "test-only")


@pytest.mark.parametrize("field,value", [
    ("tts_sample_rate", "16000"), ("tts_speaker", "other"),
    ("tts_model", "other"), ("tts_pace", 1.2), ("offline", True),
])
def test_cache_changes_with_synthesis_settings(monkeypatch, field, value):
    original = tts.cache_path("hello")
    monkeypatch.setattr(settings, field, value)
    assert tts.cache_path("hello") != original


@pytest.mark.asyncio
async def test_legacy_cache_is_bypassed_and_valid_cache_reused(monkeypatch):
    legacy = settings.tts_cache_dir / (hashlib.sha256(b"hello").hexdigest()[:16] + ".wav")
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(wav(24000))
    calls = []

    async def synthesise(text):
        calls.append(text)
        return wav()

    monkeypatch.setattr(tts, "_synthesise", synthesise)
    assert await tts.speak("hello") == wav()
    assert await tts.speak("hello") == wav()
    assert calls == ["hello"]


@pytest.mark.parametrize("audio", [wav(24000), wav(channels=2), wav(width=1), b"bad", wav()[:-4]])
@pytest.mark.asyncio
async def test_bad_provider_audio_is_not_cached(monkeypatch, audio):
    async def synthesise(text):
        return audio

    monkeypatch.setattr(tts, "_synthesise", synthesise)
    with pytest.raises(tts.TTSError):
        await tts.speak("hello")
    assert not tts.cache_path("hello").exists()


@pytest.mark.asyncio
async def test_provider_receives_supported_rate(monkeypatch):
    requests = []

    async def post(self, url, **kwargs):
        requests.append(kwargs["json"])
        return httpx.Response(200, json={"audios": [base64.b64encode(wav()).decode()]})

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    assert await tts.speak("hello") == wav()
    assert requests[0]["speech_sample_rate"] == "32000"
    assert requests[0]["output_audio_codec"] == "wav"


@pytest.mark.asyncio
async def test_offline_compound_response_is_playable(monkeypatch):
    monkeypatch.setattr(settings, "offline", True)
    audio = await tts.speak_all(["one", "two"])
    tts._validate_wav(audio)
    with wave.open(io.BytesIO(audio), "rb") as reader:
        assert reader.getnframes() == 6400


@pytest.mark.asyncio
async def test_corrupt_cache_is_regenerated(monkeypatch):
    path = tts.cache_path("hello")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"partial")

    async def synthesise(text):
        return wav()

    monkeypatch.setattr(tts, "_synthesise", synthesise)
    assert await tts.speak("hello") == wav()
    assert path.read_bytes() == wav()
