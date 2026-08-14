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

That is a real transcript, not an illustration. Saaras handled the code-mixing,
the filler and the polite interrogative ending on the first attempt.

## Where it stands

| Phase | | |
|---|---|---|
| **0 — does it understand her?** | ✅ | Saaras + Sarvam-105B resolve her speech to the right two actions |
| **1 — emitter** | firmware written, protocol verified | needs hardware to flash |
| **2 — backend** | ✅ deployed | `project-revgen.fly.dev`, verified end to end in ~3.9s |
| **3 — handheld** | ✅ **working** | press, speak, understood, spoken reply. OTA updatable. |
| **4 — harden** | not started | enclosure, battery, undo, watchdogs |

The handheld works on real hardware: one press, hold to talk, release, and the
backend returns the right IR plan with a spoken Malayalam confirmation. It
updates over WiFi, so it stays fixable once it is sealed in a case.

The emitter firmware is validated against `backend/tools/fake_emitter.py`, which
impersonates it over the real broker using the same validation rules. The only
untested part of the whole system is whether a physical IR LED flashes.

Two blockers, both waiting on parts:

- `stb.digit_1` is byte-identical to `channel_down`, a copy-paste bug inherited
  from v1. The backend refuses to fire it rather than changing the channel she
  did not ask for, so any channel containing a 1 is unavailable until the codes
  are recaptured with an IR receiver.
- Every channel number in `config/commands.json` is `null`, so `channel_set`
  correctly refuses everything. That one just needs five minutes with her
  set-top box.

## Layout

| Path | What it is | State |
|---|---|---|
| `backend/` | STT → intent → resolver → MQTT → TTS | **deployed**, 66 tests |
| `Dockerfile`, `fly.toml` | Deploy config, at the root because the image needs `config/` | live |
| `config/commands.json` | IR codes, channels, Malayalam phrases — single source of truth | needs her channel numbers |
| `firmware/selftest/` | Flash to any new board first: PSRAM, flash, WiFi survey | verified |
| `firmware/audiotest/` | Speaker bring-up: tones only, no network | verified |
| `firmware/capture/` | Phase 0 rig: recapture IR codes, sweep for discrete ones | written, untested on hardware |
| `firmware/emitter/` | IR blaster by the TV | written, untested on hardware |
| `firmware/remote/` | The handheld | **working on hardware** |
| `archive/v1/` | Superseded v1 code, kept for provenance | — |
| `docs/` | Pinouts, spec sheet, parts list | — |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Why it is built this way, and what was rejected | — |
| [`docs/BOM.md`](docs/BOM.md) | Parts, with the specs that actually matter | ₹355 outstanding |
| [`docs/WIRING.md`](docs/WIRING.md) | Pin assignment, breadboard wiring, bring-up order | — |

## Start here

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest                      # 66 tests, no network or hardware needed
```

With a Sarvam key and broker credentials in `backend/.env`:

```bash
python tools/check_sarvam.py recordings/    # does it understand her?
python tools/fake_emitter.py                # stand in for the hardware
python tools/send_wav.py recordings/01_tv_on__power_on.m4a https://project-revgen.fly.dev/command
```

See [`backend/README.md`](backend/README.md) for the detail.

## Design in one paragraph

The language model never emits button presses — it returns *goals*
(`power_on`, `volume_up`) from a fixed vocabulary, and plain Python turns goals
into IR. That split exists because IR is open-loop and most buttons are toggles:
firing `tv.power` at a television that is already on turns it off, and no model
can know which case it is in. The safety rules that prevent that live in
`backend/app/resolver.py`, which has no I/O and is entirely unit tested.

## A note on secrets

This repo is public. A Groq key was committed in `.env` in April 2025 and had to
be revoked. Credentials now live in gitignored files — `backend/.env` and
`firmware/emitter/secrets.h` — with committed `.example` templates alongside.
Assume anything pushed here is scraped within minutes.
