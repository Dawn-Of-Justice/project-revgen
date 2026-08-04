"""RevGen backend.

    POST /command   multipart audio in, Malayalam WAV out.

That is the entire contract with the remote. The remote knows nothing about
devices, IR, channels or Malayalam -- it is a microphone with a network stack.

The remote sends WAV, but the endpoint accepts anything Saaras can read --
MP3, M4A, OGG, OPUS and the rest -- so phone recordings can be curled straight
at it during testing without converting them first.

The pipeline is intentionally linear and every stage can fail loudly:

    WAV -> Saaras -> Sarvam-105B -> resolver -> MQTT -> ack -> Bulbul (cached)

Every exit path returns audio, including the failures. Silence is
indistinguishable from a dead device, and that is when she stops using it.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

import secrets

from fastapi import FastAPI, Header, HTTPException, Response, UploadFile
from fastapi.responses import JSONResponse

from . import audio, logbook, resolver
from .catalog import Catalog
from .config import settings
from .emitter import EmitterOffline, EmitterTimeout, emitter
from .intent import IntentError, extract
from .resolver import State
from .schemas import Intent
from .stt import STTError, transcribe
from .tts import speak_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("revgen")

catalog = Catalog.load(settings.catalog_path)
state = State()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await emitter.connect()
    yield
    await emitter.close()


app = FastAPI(title="RevGen", lifespan=lifespan)


def _authorise(token: str | None) -> None:
    """Shared secret between the remote and the backend.

    Not sophisticated, but the threat is a public URL that anyone can POST
    audio at to control her television, and a constant-time compare against a
    device token closes that. Empty token disables the check for LAN use.
    """
    if not settings.device_token:
        return
    if not token or not secrets.compare_digest(token, settings.device_token):
        raise HTTPException(status_code=401, detail="bad or missing device token")


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "emitter_online": emitter.online,
        "offline_mode": settings.offline,
        "channels_configured": sum(
            1 for name in catalog.channel_names() if catalog.channel_number(name)
        ),
        "audio_formats": sorted(
            e.lstrip(".") for e in audio.SUPPORTED_EXTENSIONS
        ),
    }


@app.post("/command")
async def command(
    file: UploadFile,
    x_revgen_token: str | None = Header(default=None),
) -> Response:
    _authorise(x_revgen_token)

    started = time.monotonic()
    data = await file.read()

    if len(data) > settings.max_upload_bytes:
        # Refuse before paying Saaras to transcribe whatever this is.
        raise HTTPException(status_code=413, detail="audio too large")

    transcript = ""
    intents: list[Intent] = []
    phrase_key = "err.internal"
    texts: list[str] = []

    # Sniffed from the bytes, not the filename -- phones lie about both the
    # extension and the content type. Recorded only for the log; transcribe()
    # detects it again itself so it stays usable standalone.
    fmt = audio.sniff(data)

    try:
        transcript = await transcribe(data, file.filename or "command.wav")
        intents = await extract(transcript, catalog)

        plan = resolver.resolve(
            intents,
            catalog,
            state,
            now=time.time(),
            debounce_s=settings.power_debounce_s,
            max_volume_steps=settings.max_volume_steps,
            digit_gap_ms=settings.digit_gap_ms,
            max_actions=settings.max_actions,
            post_power_delay_ms=settings.post_power_delay_ms,
        )
        phrase_key = plan.phrase_key

        if plan.fires_ir:
            ack = await emitter.send(plan)
            if not ack.ok:
                phrase_key = "err.no_ack"

        if phrase_key == "err.no_ack":
            texts = [catalog.phrase("err.no_ack")]
        else:
            texts = [catalog.phrase(p.key, **p.args) for p in plan.phrases]

    except STTError as exc:
        log.warning("stt failed: %s", exc)
        phrase_key, texts = "err.not_understood", [catalog.phrase("err.not_understood")]
    except IntentError as exc:
        log.warning("intent failed: %s", exc)
        phrase_key, texts = "err.internal", [catalog.phrase("err.internal")]
    except EmitterOffline as exc:
        log.warning("emitter offline: %s", exc)
        phrase_key, texts = "err.emitter_offline", [catalog.phrase("err.emitter_offline")]
    except EmitterTimeout as exc:
        log.warning("no ack: %s", exc)
        phrase_key, texts = "err.no_ack", [catalog.phrase("err.no_ack")]
    except Exception:
        log.exception("unhandled")
        phrase_key, texts = "err.internal", [catalog.phrase("err.internal")]

    reply = " ".join(texts)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    logbook.record(
        transcript=transcript,
        intents=[i.model_dump(mode="json") for i in intents],
        outcome=phrase_key,
        reply=reply,
        elapsed_ms=elapsed_ms,
        bytes_in=len(data),
        audio_format=fmt.name if fmt else "unknown",
    )
    log.info(
        "%sms  [%s %dB]  %r -> %s",
        elapsed_ms,
        fmt.name if fmt else "unknown",
        len(data),
        transcript,
        phrase_key,
    )

    try:
        spoken = await speak_all(texts)
    except Exception:
        # Even TTS failing must not produce a silent response.
        log.exception("tts failed")
        return JSONResponse(
            {"outcome": phrase_key, "reply": reply, "audio": False}, status_code=200
        )

    return Response(
        content=spoken,
        media_type="audio/wav",
        headers={
            "X-RevGen-Outcome": phrase_key,
            "X-RevGen-Elapsed-Ms": str(elapsed_ms),
        },
    )
