# RevGen backend

Holds roughly 80% of the system's complexity so that both firmwares can stay
boring. That split is the direct lesson from v1, where the smartest component
was a microcontroller in someone else's house.

```
audio -> Saaras (STT) -> Sarvam-105B (intent) -> resolver -> MQTT -> ack -> Bulbul (cached)
```

**Status: deployed and verified end to end.** Live at
`project-revgen.fly.dev`, one machine in `bom`. A real recording of her voice
returns the correct IR sequence and a spoken Malayalam confirmation.

## Run it locally

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # requirements.txt alone = runtime only
cp .env.example .env                  # Sarvam key + broker credentials
uvicorn app.main:app --reload
```

No key and no broker? `OFFLINE=true` runs the whole chain with stubs — enough to
check wiring and exercise the resolver.

## Tools

| Script | What it does |
|---|---|
| `tools/check_sarvam.py` | Batch-transcribes a folder of recordings and prints the resolved intents. Scores accuracy if files are named `01_tv_on__power_on.m4a`. |
| `tools/fake_emitter.py` | Impersonates the IR emitter over the real broker: validates commands with the same rules as the firmware, prints each step, publishes an ack. |
| `tools/send_wav.py` | Posts an audio file at the backend and plays the reply. Saves it as `reply.wav` in the current directory. |
| `tools/build_tts_cache.py` | Pre-generates every Malayalam phrase. Throttled to one request per 2.1s for the bulbul:v3 rate limit. |

## Testing without hardware

**1. Unit tests.** No network, no hardware:

```bash
pytest          # 66 tests
```

**2. Does it understand her?** The go/no-go on the whole premise:

```bash
python tools/check_sarvam.py recordings/
```

Target is 95% intent accuracy. Include three or four recordings with the TV
playing and no command spoken, named `__unknown` — refusing ambient speech is
the failure mode that decides whether this is usable in her living room.

**3. The full chain.** With `MQTT_*` set in `.env`, run the fake emitter in one
terminal and send a recording from another:

```bash
python tools/fake_emitter.py
python tools/send_wav.py recordings/01_tv_on__power_on.m4a https://project-revgen.fly.dev/command
```

The fake emitter prints the decoded IR steps and acks, so the backend returns
the real confirmation rather than `err.emitter_offline`. Everything except the
physical LED is proven at that point.

## Measured latency

Deployed instance, 155KB m4a from a laptop in Kerala:

| | ms |
|---|---|
| Server total | 1,732 |
| — MQTT round trip via Frankfurt | ~160 |
| Network (upload) | 2,158 |
| **End to end** | **3,890** |

Two things this settles. The EU broker costs ~160ms, not the ~500ms feared, so
self-hosting Mosquitto is not worth doing. And **upload dominates** — that test
file is mostly silence, and a tight 2–3s utterance (~96KB at the measured
72KB/s) lands near 3s. Stopping the recording on silence is therefore the
highest-value firmware behaviour, worth more than any backend optimisation.

## Deploy (Fly.io)

`Dockerfile` and `fly.toml` live at the **repo root**, not here — the image
needs `config/commands.json`, which sits outside `backend/` because the emitter
firmware reads the same file. All `fly` commands run from the repo root, since
that is where `fly.toml` is.

Already provisioned: app `project-revgen`, region `bom`, one machine, volume
`revgen_data` mounted at `/data`. Routine redeploy is just:

```bash
fly deploy
```

Secrets currently set — `SARVAM_API_KEY`, `DEVICE_TOKEN`, `MQTT_HOST`,
`MQTT_USERNAME`, `MQTT_PASSWORD`. Non-secret config (`DATA_DIR`, `MQTT_PORT`,
`MQTT_TLS`) is in `fly.toml`. Each `fly secrets set` restarts the machine.

**`MQTT_HOST` must be a secret, not `fly.toml` config** — `fly.toml` is
committed to a public repo.

If rebuilding from scratch:

```bash
fly launch --no-deploy
fly volumes create revgen_data --region bom --size 1   # only after the app exists
# uncomment [[mounts]] in fly.toml
fly secrets set SARVAM_API_KEY=... MQTT_HOST=... MQTT_USERNAME=... MQTT_PASSWORD=... DEVICE_TOKEN=...
fly deploy
fly ssh console -C "python tools/build_tts_cache.py"
```

On Windows use one `fly secrets set` per line rather than backslash
continuations. Generate the token with
`python -c "import secrets;print(secrets.token_urlsafe(32))"`.

### Never scale past one machine

```
min_machines_running = 1       # keep it warm: a cold start hits the first
auto_stop_machines   = 'off'   # command of the morning, when she is least patient
```

The power debounce and the rate limiter both live in process memory. A second
machine keeps its own copies, so the rule that stops her repeated "TV on" from
switching the set back off silently stops working. Scaling out requires moving
`resolver.State` to a shared store first — it is the reason this is not on
serverless.

Fly's launcher created **two** machines despite `min_machines_running = 1`; that
had to be corrected with `fly scale count 1`. Worth re-checking after any
`fly launch`, which also rewrites `fly.toml` and strips its comments.

The volume holds the TTS cache and the utterance log, so both survive redeploys.
Without it every deploy regenerates ~20 phrases against the bulbul:v3 rate limit
and throws away the log needed to debug her problems from a distance.

## Layout

| File | Why it exists |
|---|---|
| `app/main.py` | The two endpoints. Every exit path returns audio, including failures. |
| `app/resolver.py` | Every rule that decides whether IR fires. Pure functions, no I/O. |
| `app/intent.py` | Forced tool calling, so the model cannot emit a command outside the vocabulary. |
| `app/catalog.py` | Refuses to fire codes flagged broken instead of silently sending the wrong one. |
| `app/emitter.py` | MQTT client. Waits for an ack; never assumes a published message arrived. |
| `app/ratelimit.py` | Spend guard. Bounds what a wedged client can cost overnight. |
| `app/audio.py` | Sniffs the container from its bytes, so phone recordings work unconverted. |
| `app/tts.py` | Bulbul with a disk cache. Concatenates clips for compound replies. |
| `app/logbook.py` | One JSON line per utterance. The alternative is debugging by phone. |
| `app/schemas.py` | The two wire contracts — remote↔backend and backend↔emitter. |

## Audio formats

The remote sends WAV. Everything else Saaras reads is accepted too — MP3,
M4A/MP4, AAC, OGG, OPUS, FLAC, AIFF, AMR, WMA, WebM — so voice memos work
unconverted.

Format is detected from the file header rather than the extension, because
iPhones write `.m4a`, Android tends toward `.mp3` or `.opus`, WhatsApp
re-encodes to `.ogg`, and multipart uploads often arrive named `blob`.

Nothing is transcoded. One caveat: Saaras works best at 16 kHz mono and phone
recordings are usually 44.1/48 kHz stereo. They transcribe fine, but if
`check_sarvam.py` accuracy looks worse than expected, rule this out before
blaming the model:

```bash
ffmpeg -i in.m4a -ar 16000 -ac 1 out.wav
```

## Things that look like details but are not

**`POWER_DEBOUNCE_S`** is the single most important setting. Power is a toggle,
so if she repeats "TV on" while the set is still waking up, the second command
undoes the first. Eight seconds of suppression removes the dominant real-world
failure. It stops mattering the moment `discrete.power_on` is filled in from the
Phase 0 sweep, and the resolver switches over on its own.

**The TTS cache is a latency mechanism, not a cost one.** Cached playback is
instant; a live Bulbul call would add most of a second to every reply.

**The instant acknowledgement is a local beep on the device, not this reply.**
Measured round trip is ~3s and upload dominates, so no backend work brings the
spoken confirmation under ~1.2s. Splitting the two — a beep the moment she stops
speaking, the Malayalam reply when it completes — answers the question she
actually has ("did it hear me?") at zero latency.

**Refusing is a feature.** The microphone sits in a room with a loud television,
so "this was not a command" is a common correct answer. The intent prompt
prefers `unknown` over a guess, and the resolver fires nothing on low confidence.

**`reasoning_effort` must be sent as an explicit `null`.** Sarvam defaults it to
`"medium"`, and omitting the key leaves reasoning switched on — which consumed
the entire token budget and returned an empty response with no tool call. That
looked exactly like the model failing to understand her, and cost ~1.3s per
request besides.

## Cost and limits

At 50 commands/day of ~4s each, against
[Sarvam's published rates](https://docs.sarvam.ai/api-reference-docs/pricing):

| | Rate | Monthly |
|---|---|---|
| Saaras STT | ₹30/hour, billed per second | ~₹50 |
| Sarvam-105B | ₹4 in / ₹16 out per 1M tokens | ~₹5 |
| Bulbul v3 | ₹30/10K chars | ~₹0 (cached) |
| **Total** | | **~₹55** |

Sarvam-30B is listed in the docs but rejected by the live API as deprecated, so
this runs on Sarvam-105B. The intent call is a few hundred tokens against
~₹50/month of audio, so the pricier model barely moves the total.

New accounts get ₹100 in credits. Rate limits on the Starter plan: 60 req/min
for STT, 40 req/min for Sarvam-105B, 30 req/min for bulbul:v3 — all far beyond
one household, but the TTS one is why `build_tts_cache.py` throttles itself.

**The spend guard** caps 20 requests/minute and 200/day. The minute limit
catches the realistic disaster — a firmware retry loop hammering `/command`
overnight — and the daily cap is the backstop, bounding a bad day at roughly ₹7.
Both sit above `file.read()`, so a throttled request never reaches Saaras.
Watch `requests.today` on `/health` climbing while nobody is using it; that is
what a wedged client looks like from outside.
