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
| `backend/` | STT → intent → resolver → MQTT → TTS | **deployed & verified end to end**, 66 tests |
| `Dockerfile`, `fly.toml` | Deploy config (root, because the image needs `config/`) | ready |
| `config/commands.json` | IR codes, channels, Malayalam phrases — single source of truth | needs her channel numbers |
| `firmware/emitter/` | IR blaster by the TV | **written**, protocol verified; untested on hardware |
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

Phases 0 and 2 are done. Saaras transcribed her first recording correctly —
code-mixing, filler and a polite interrogative ending intact — and the deployed
backend turns it into the right five-step IR sequence and answers in Malayalam,
end to end in ~3.9s (upload dominates; see ARCHITECTURE.md).

The emitter firmware is written and validated against
`backend/tools/fake_emitter.py`, which impersonates it over the real broker and
enforces the same rules. Once the parts arrive it needs flashing and pointing at
a TV — after that the handheld is the only unknown left in the system.

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
