# RevGen

A voice-controlled replacement for two remote controls, in Malayalam.

Built for a grandmother who knows perfectly well what the television and the
set-top box are — she just cannot tell which of the two remotes does what. She
presses one button, says what she wants, and hears a confirmation.

```
"TV ഓണാക്കുവോ? ഉം. and sound-ഉം കൂടെ കൂട്ടണേ കുറച്ച്."
   → tv.power, wait 2.5s, tv.volume_up ×2
   → "ടിവി ഓണാക്കി. ശബ്ദം കൂട്ടി."
```

## Layout

| Path | What it is | State |
|---|---|---|
| `backend/` | STT → intent → resolver → MQTT → TTS | **working**, 66 tests |
| `Dockerfile`, `fly.toml` | Deploy config (root, because the image needs `config/`) | ready |
| `config/commands.json` | IR codes, channels, Malayalam phrases — single source of truth | needs her channel numbers |
| `firmware/emitter/` | IR blaster by the TV | **written**, MQTT + LWT; untested on hardware |
| `firmware/remote/` | The handheld | not started (XIAO ESP32S3 + custom PCB) |
| `archive/v1/` | Superseded v1 code, kept for provenance | — |
| `docs/` | Pinouts, spec sheet, parts list | — |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Why it is built this way, and what was rejected | — |
| [`docs/BOM.md`](docs/BOM.md) | Parts to buy, with the specs that actually matter | ~₹8,100 |

## Start here

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest                      # 66 tests, no network or hardware needed
```

Then, with a Sarvam key in `backend/.env`:

```bash
python tools/check_sarvam.py recordings/     # does it understand her?
uvicorn app.main:app --reload
python tools/send_wav.py recordings/tv_on.m4a
```

See [`backend/README.md`](backend/README.md) for the detail.

## Where it stands

Phase 0 passed — Saaras transcribed her first recording correctly, including
code-mixing, filler and a polite interrogative ending. Phase 2 (backend) is
written and tested.

Next is the emitter: `firmware/emitter/emitter.ino` already parses the command
grammar over serial, so the work is replacing `Serial.readString()` with an MQTT
callback. After that a recorded WAV from a laptop can control the TV, and the
handheld is the only unknown left in the system.

Two known-bad IR codes are flagged in `config/commands.json` and the backend
refuses to fire them rather than sending the wrong signal. Recapturing needs a
TSOP1838; nothing else is blocked on it.

## Design in one paragraph

The language model never emits button presses — it returns *goals*
(`power_on`, `volume_up`) from a fixed vocabulary, and plain Python turns goals
into IR. That split exists because IR is open-loop and most buttons are toggles:
firing `tv.power` at a TV that is already on turns it off, and no model can know
which case it is in. The safety rules that prevent that live in
`backend/app/resolver.py`, which has no I/O and is entirely unit tested.
