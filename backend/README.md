# RevGen backend

Holds roughly 80% of the system's complexity so that both firmwares can stay
boring. That split is the direct lesson from v1, where the smartest component
was a microcontroller in someone else's house.

```
WAV -> Saaras (STT) -> Sarvam-30B (intent) -> resolver -> MQTT -> ack -> Bulbul (cached)
```

## Run it

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # requirements.txt alone = runtime only
cp .env.example .env                  # add your Sarvam key
uvicorn app.main:app --reload
```

No key and no broker? `OFFLINE=true` runs the whole chain with stubs, which is
enough to check the wiring and exercise the resolver.

## The order to do things in

**1. Prove the premise.** Before anything else, record her on a phone saying
20 real commands and run:

```bash
python tools/check_sarvam.py recordings/
```

If Saaras cannot handle her Malayalam, nothing downstream matters. Target is
95% intent accuracy. This costs an evening and the signup credits.

**2. Run the safety tests.** No network, no hardware:

```bash
pytest
```

**3. Prove the chain.** With the emitter flashed and Mosquitto running, a
recorded WAV from your laptop should control the TV:

```bash
python tools/build_tts_cache.py
python tools/send_wav.py recordings/tv_on.wav
```

That is the Phase 2 acceptance test. When it passes, the handheld is the only
unknown left in the system.

## Deploy (Fly.io)

`Dockerfile` and `fly.toml` live at the **repo root**, not here — the image
needs `config/commands.json`, which sits outside `backend/` because the emitter
firmware reads the same file.

You need an MQTT broker both sides can reach. The emitter is behind her home
NAT, so it must be one the emitter dials out to — HiveMQ Cloud's free tier
(100 connections) is more than enough.

```bash
cd ..                       # repo root
fly launch --no-deploy      # claim the app name, keep the existing fly.toml
fly volumes create revgen_data --region bom --size 1

fly secrets set \
  SARVAM_API_KEY=sk_xxx \
  MQTT_HOST=xxxxx.s1.eu.hivemq.cloud \
  MQTT_USERNAME=revgen \
  MQTT_PASSWORD=... \
  DEVICE_TOKEN=$(python -c "import secrets;print(secrets.token_urlsafe(32))")

fly deploy
fly ssh console -C "python tools/build_tts_cache.py"   # onto the volume, once
curl https://revgen.fly.dev/health
```

`DEVICE_TOKEN` matters the moment this has a public URL — without it anyone who
finds the hostname can POST audio and control her television. The remote sends
it as `X-RevGen-Token`.

### Never scale past one machine

```
min_machines_running = 1     # keep it warm: a cold start blows the 1.2s budget
                             # on the first command of the morning
auto_stop_machines  = false
```

And do not raise the count. The power debounce lives in process memory, so a
second machine keeps its own timer and the rule that stops her repeated "TV on"
from switching the set back off silently stops working. Scaling out requires
moving `resolver.State` to a shared store first — it is the reason this is not
on serverless.

`primary_region = "bom"` because every 100ms of network latency comes straight
out of the confirmation budget.

The volume holds the TTS cache and the utterance log, so both survive
redeploys. Without it every deploy would regenerate ~20 phrases against the
bulbul:v3 rate limit and throw away the log you need to debug her problems from
a distance.

## Layout

| File | Why it exists |
|---|---|
| `app/resolver.py` | Every rule that decides whether IR fires. Pure functions, no I/O. |
| `app/intent.py` | Forced tool calling, so the model cannot emit a command outside the vocabulary. |
| `app/catalog.py` | Refuses to fire codes flagged broken instead of silently sending the wrong one. |
| `app/emitter.py` | Waits for an ack. Never assumes a published message arrived. |
| `app/logbook.py` | One JSON line per utterance. The alternative is debugging by phone. |
| `app/audio.py` | Sniffs the container from its bytes, so phone recordings work unconverted. |

## Audio formats

The remote always sends WAV. Everything else Saaras reads is accepted too --
MP3, M4A/MP4, AAC, OGG, OPUS, FLAC, AIFF, AMR, WMA, WebM -- so you can point
`send_wav.py` and `check_sarvam.py` straight at voice memos off a phone.

Format is detected from the file header rather than the extension, because
iPhones write `.m4a`, Android tends toward `.mp3` or `.opus`, WhatsApp
re-encodes to `.ogg`, and multipart uploads often arrive named `blob`.

Nothing is transcoded. One caveat worth knowing: Saaras works best at 16 kHz
mono, and phone recordings are usually 44.1 or 48 kHz stereo. They transcribe
fine, but if `check_sarvam.py` accuracy looks worse than expected, rule this out
before blaming the model:

```bash
ffmpeg -i in.m4a -ar 16000 -ac 1 out.wav
```

## Things that look like details but are not

**`POWER_DEBOUNCE_S`** is the single most important setting. Power is a toggle,
so if she repeats "TV on" while the set is still waking up, the second command
undoes the first. Eight seconds of suppression removes the dominant real-world
failure. It stops mattering the moment `discrete.power_on` is filled in from
the Phase 0 sweep, and the resolver switches over on its own.

**The TTS cache** is a latency mechanism, not a cost one. Playback has to begin
within ~1.2s of her finishing, because fast confirmation is what stops the
repetition in the first place.

**Refusing is a feature.** The microphone sits in a room with a loud television,
so "this was not a command" is a common correct answer. The intent prompt is
written to prefer `unknown` over a guess, and the resolver fires nothing on low
confidence.

## Cost

At 50 commands/day of ~4s each, against
[Sarvam's published rates](https://docs.sarvam.ai/api-reference-docs/pricing):

| | Rate | Monthly |
|---|---|---|
| Saaras STT | ₹30/hour, billed per second | ~₹50 |
| Sarvam-105B | ₹4 in / ₹16 out per 1M tokens | ~₹5 |
| Bulbul v3 | ₹30/10K chars | ~₹0 (cached) |
| **Total** | | **~₹55** |

Sarvam-30B is listed in the docs but rejected by the live API as deprecated, so
this runs on Sarvam-105B. It is the more expensive model, but the intent call is
a few hundred tokens against ~₹50/month of audio, so it barely moves the total.

New accounts get ₹100 in credits, so the first couple of months are free.
Starter plan allows 60 req/min, which is far beyond one household.
