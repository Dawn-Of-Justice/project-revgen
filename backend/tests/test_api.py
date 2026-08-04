"""End-to-end through the HTTP layer, in offline mode.

No Sarvam key, no broker, no hardware. This is the only coverage `main.py` has,
and it exists mainly to catch the boring failures -- a renamed import, a wrong
header, a response that comes back silent -- which are exactly the ones that
would otherwise surface as a dead device in someone else's living room.
"""

from __future__ import annotations

import io
import math
import struct
import wave

import pytest
from fastapi.testclient import TestClient

from app.config import settings


def wav_bytes(seconds: float = 0.3, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(
            b"".join(
                struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate)))
                for i in range(int(rate * seconds))
            )
        )
    return buf.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Offline stubs the three network calls; tmp_path keeps the TTS cache and
    # the utterance log out of the repo.
    monkeypatch.setattr(settings, "offline", True)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "device_token", "")

    from app import main
    from app.ratelimit import Limiter
    from app.resolver import State

    # main.state and main.limiter are module-level singletons -- deliberately,
    # since both must outlive a request. That also means they leak between
    # tests, so each one starts from a clean slate.
    monkeypatch.setattr(main, "state", State())
    monkeypatch.setattr(main, "limiter", Limiter(per_minute=1000, per_day=10_000))

    with TestClient(main.app) as c:
        yield c


def post(client, data=None, **kwargs):
    return client.post(
        "/command",
        files={"file": ("command.wav", data if data is not None else wav_bytes(), "audio/wav")},
        **kwargs,
    )


# --- health -------------------------------------------------------------


def test_health_reports_readiness(client):
    body = client.get("/health").json()
    assert body["ok"] is True
    assert "wav" in body["audio_formats"]
    assert "m4a" in body["audio_formats"]


# --- the happy path -----------------------------------------------------


def test_command_returns_audio_and_an_outcome(client):
    response = post(client)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/")
    assert response.headers["X-RevGen-Outcome"]
    assert int(response.headers["X-RevGen-Elapsed-Ms"]) >= 0
    assert len(response.content) > 0, "a silent reply is indistinguishable from a dead device"


def test_every_response_carries_an_outcome_header(client):
    """Whatever happens, the caller must be able to tell what happened."""
    for payload in (wav_bytes(), b"not audio at all", b""):
        response = post(client, payload)
        assert response.status_code == 200
        assert response.headers.get("X-RevGen-Outcome")


def test_unreadable_audio_still_answers(client):
    """Garbage in still produces speech out, never a silent 500.

    The outcome key is not asserted: offline mode short-circuits inside
    transcribe() before format detection runs, so every input yields the same
    stub transcript. Real format rejection is covered in test_audio.py.
    """
    response = post(client, b"\x00" * 64)
    assert response.status_code == 200
    assert len(response.content) > 0


# --- guards -------------------------------------------------------------


def test_oversized_upload_is_refused_before_paying_for_stt(client, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 1000)
    assert post(client, wav_bytes(seconds=2.0)).status_code == 413


def test_token_is_required_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "device_token", "correct-horse")
    assert post(client).status_code == 401
    assert post(client, headers={"X-RevGen-Token": "wrong"}).status_code == 401
    assert post(client, headers={"X-RevGen-Token": "correct-horse"}).status_code == 200


def test_burst_gets_429_without_touching_sarvam(client, monkeypatch):
    from app import main, stt
    from app.ratelimit import Limiter

    calls: list[str] = []
    monkeypatch.setattr(main, "limiter", Limiter(per_minute=3, per_day=100))
    monkeypatch.setattr(stt, "transcribe", lambda *a, **k: calls.append("stt"))

    codes = [post(client).status_code for _ in range(6)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3:] == [429, 429, 429]
    assert "Retry-After" in post(client).headers
    assert calls == [], "a throttled request must not reach Saaras"


def test_daily_cap_answers_in_malayalam_rather_than_a_bare_429(client, monkeypatch):
    """Heavy use might be genuine, so she is told out loud instead of ignored."""
    from app import main
    from app.ratelimit import Limiter

    monkeypatch.setattr(main, "limiter", Limiter(per_minute=1000, per_day=2))
    post(client)
    post(client)

    capped = post(client)
    assert capped.status_code == 200
    assert capped.headers["X-RevGen-Outcome"] == "err.rate_limited"
    assert len(capped.content) > 0


def test_rejected_request_has_no_side_effects(client, monkeypatch):
    """A 401 must not transcribe and must not fire IR.

    The status code alone is not the guarantee worth having -- what matters is
    that an unauthorised caller cannot change her television, and cannot run up
    a Sarvam bill either. _authorise() is the first statement in the handler,
    ahead of file.read(), so nothing downstream is reached.
    """
    from app import main, stt

    calls: list[str] = []
    monkeypatch.setattr(settings, "device_token", "correct-horse")
    monkeypatch.setattr(stt, "transcribe", lambda *a, **k: calls.append("stt"))
    monkeypatch.setattr(main.emitter, "send", lambda *a, **k: calls.append("ir"))

    assert post(client).status_code == 401
    assert post(client, headers={"X-RevGen-Token": "nope"}).status_code == 401
    assert calls == [], "unauthorised request reached STT or the emitter"


def test_no_token_configured_means_open(client):
    assert post(client).status_code == 200


# --- the debounce, over HTTP -------------------------------------------


def test_repeated_power_command_is_suppressed_across_requests(client):
    """The safety rule has to survive the request boundary, not just the unit test.

    This is also the test that fails the moment anyone scales the service past
    one machine, because State lives in process memory.
    """
    first = post(client)
    second = post(client)

    assert first.headers["X-RevGen-Outcome"].startswith("tv.")
    assert second.headers["X-RevGen-Outcome"] == "err.too_soon"
