# RevGen v2 — architecture

Replaces the v1 design. Kept separate from the README because the *reasoning*
matters more than the instructions: most of what follows is the record of ideas
that were tried and rejected, and re-deriving that later would be expensive.

**Target user:** an elderly Malayalam speaker who uses this daily, alone.
She knows the difference between the television and the set-top box; what she
cannot do is work out which of two remotes to pick up. That is the problem
being solved, and it drives everything below.

---

## 1. Three components, two interfaces

```
┌──────────────┐  HTTPS  ┌──────────────┐   MQTT   ┌──────────────┐
│  REMOTE      │ ──────▶ │  BACKEND     │ ───────▶ │  IR EMITTER  │
│  handheld    │  audio  │  Pi or cloud │   JSON   │  by the TV   │
│              │ ◀────── │              │ ◀─────── │              │
│ ESP32-S3     │  WAV    │ STT, intent, │   ack    │ ESP32        │
│ button, mic, │  reply  │ resolver,    │          │ 4x IR LED    │
│ speaker      │         │ TTS, logs    │          │ mains power  │
└──────────────┘         └──────────────┘          └──────────────┘
```

Only two boundaries exist, and if both are stable all three components can be
built independently and in any order:

| Interface | Contract |
|---|---|
| Remote → Backend | `POST /command`, multipart audio in, WAV out |
| Backend → Emitter | command sequence on `revgen/emitter/cmd`, `Ack` on `.../ack` |

Both are testable without the other side: `curl` a WAV at the backend,
`mosquitto_pub` at the emitter.

**Roughly 80% of the complexity lives in the backend on purpose.** v1 stalled
because its smartest component was a microcontroller in someone else's house.
Smart firmware is firmware you cannot debug remotely.

**IR codes live in the backend, not the emitter.** The backend sends full
descriptors (`{protocol, address, command}`), so the emitter can stay dumb and
permanent. Adding her AC later means editing a JSON file, not reflashing a board
you would have to drive to.

---

## 2. The hard problem is not voice

It is that **IR is open-loop and most buttons are toggles.**

She says "TV on". The system fires `tv.power`. If the TV was already on, it just
turned it *off*. No amount of model quality fixes this, because the model is not
the ignorant part — the system is. There is no sensor anywhere in the loop, so
there is no information about physical state for any intelligence to reason over.

Three approaches were considered:

**Sense the room.** A photodiode on the screen, HDMI-CEC power queries, an
energy-monitoring plug. Genuinely solves it, and CEC in particular gives an
idempotent "turn on and switch to this input" via `<Image View On>` +
`<Active Source>`. Deferred, not rejected — see §6.

**Design the state away.** Leave the box permanently on, never change TV input,
so only TV power is stateful. Rejected: it assumes nobody else in the house ever
touches anything, which is false.

**Let her be the sensor.** Adopted. She only says "TV on" while looking at a TV
that is off. A person in front of the device is a better state sensor than
anything that could be taped to it.

### The failure that survives

Not unknown state — **impatient repetition**. She says "TV on", the set takes
three seconds to show a picture, she assumes it did not hear her, repeats, and
the second toggle undoes the first.

Two fixes, both nearly free:

1. **Acknowledge instantly, confirm when done.** Two sounds, not one:

   - **A local beep the moment she stops speaking**, generated on the device.
     Zero network, zero latency. This is what actually stops the repetition,
     because the thing she is uncertain about is whether it *heard* her.
   - **The Malayalam confirmation** when the round trip completes, telling her
     what was done.

   The original design put the whole burden on the spoken reply and set a 1.2s
   budget for it. Measured on the deployed backend that is not achievable:
   ~1.6s server-side plus upload, and upload does not shrink in production --
   six seconds of 16kHz mono WAV is 192KB, larger than a compressed phone
   recording of the same utterance.

   Splitting the two makes the hard number a firmware concern (a beep, which is
   free) and leaves the spoken reply on a soft ~3s target. The TTS cache still
   matters, but for the reply rather than the acknowledgement.
2. **Debounce power commands** for 8 seconds per device, and say
   "ഒന്ന് കാത്തിരിക്കൂ" instead of firing.

Both stop mattering the moment discrete power codes are found (§6), and the
resolver switches over on its own when they are.

---

## 3. The LLM does not emit buttons

An earlier draft had the model returning `["tv.power", "delay 2000", "stb.power"]`
directly. That is wrong: the correct button sequence depends on state the model
cannot see, so it would be *guessing* — the last place you want a probabilistic
component.

Instead the model returns **goals** from a fixed vocabulary
(`power_on`, `volume_up`, `channel_set`…), and `app/resolver.py` — pure Python,
no I/O — turns goals plus known state into a button sequence.

The split is not about trusting the model more or less. It is about putting the
model where ambiguity actually lives:

| | Handles |
|---|---|
| Saaras + Sarvam-105B | Malayalam, code-mixing, politeness, synonyms, rambling |
| Plain Python | timers, toggle safety, retry limits, whitelist validation |

"Was a power command sent in the last 8 seconds" is a timestamp subtraction. It
belongs nowhere near a language model.

Output is constrained by **forced tool calling** (`tool_choice` pinned to one
function), so the model cannot reply with prose or invent a command outside the
enum. Anything failing validation is discarded rather than repaired.

### Compound utterances are normal

The first real recording was:

```
"TV ഓണാക്കുവോ? ഉം. and sound-ഉം കൂടെ കൂട്ടണേ കുറച്ച്."
```

One breath, two requests, a filler, and a mid-sentence language switch. An
early schema allowed one action per utterance and the model correctly returned
`unknown` rather than dropping half of what she said. The schema now takes a
list, and the resolver:

- inserts a **2.5s wait after `power_on`** — a booting TV is not listening, and
  without the gap "turn it on and turn it up" silently never changes the volume;
- reports **partial success honestly** — if power is debounced but volume works,
  she hears about the volume rather than an apology;
- **bounds the action count** so a garbled transcript cannot become a burst.

---

## 4. Speech

`saaras:v3`, `mode=codemix`, `language_code=ml-IN`.

Codemix keeps English words in Latin script and Malayalam in native script,
which is exactly how she speaks and the form the intent model reads best.
Setting the language explicitly skips detection — faster, and one fewer failure
mode. If accuracy disappoints, `mode=transcribe` is the first thing to A/B; it
is the biggest single lever.

**Refusing is a feature.** The microphone sits in a room with a loud television,
so "this was not a command" is a common correct answer. The prompt prefers
`unknown` over a guess and the resolver fires nothing on low confidence.

---

## 5. Build order

Each phase ends in something testable. Do not move on until it works.

**0 — Prove the premise.** Record her on a phone, run
`backend/tools/check_sarvam.py`. If Saaras cannot handle her Malayalam nothing
downstream matters. Costs an evening. ✅ *Passed on first attempt.*

**1 — Emitter on MQTT.** `firmware/emitter/emitter.ino` already parses the
command grammar over serial; replace `Serial.readString()` with an MQTT
callback. An afternoon, using hardware you already own. Ends with: you control
the TV from a terminal.

**2 — Backend end to end.** ✅ *Written.* Ends with: a recorded WAV from your
laptop controls the TV, whole intelligence layer proven, no new hardware.

**3 — Voice unit.** Last on purpose. By now it is the only unknown left. v1
failed partly because this was built first, and it is the component with the
least observable failure modes.

**4 — Harden.** Enclosure, battery warning by voice, WiFi loss handling,
watchdogs, undo.

---

## 6. Deferred, with reasons

**IR code recapture.** `archive/v1/signal.json` codes were captured from real
remotes and mostly work. `stb.digit_1` is provably a copy-paste of `channel_down`
and `tv.apps` is malformed. The catalog refuses both rather than firing them, so
this is not blocking — but any channel containing a 1 is unusable until a
TSOP1838 arrives.

**The discrete-code sweep.** While the receiver is wired up, sweep the whole
Panasonic command space (address `0x8`, commands `0x00`–`0xFF`) with a camera on
the TV rather than only capturing buttons that physically exist. Manufacturers
usually ship discrete power-on/off codes that are not on the remote. Fill them
into `config/commands.json` under `discrete` and the toggle problem disappears
entirely — the resolver detects them and stops debouncing.

**HDMI-CEC.** An ESP32 can speak CEC natively over 3 GPIOs at 3.3V. Tapped
between the box and the TV it inherits that port's physical address, so
`<Image View On>` + `<Active Source>` becomes an idempotent "turn on and show
the box". Needs VIERA Link enabled in the TV menu and an HDMI breakout. The
strongest available upgrade if the human-as-sensor approach proves insufficient.

**Screen photodiode.** Sampled over ~2s, variance distinguishes real content
(flickers) from a no-signal screen (static). Brand-agnostic, needs no CEC, and
measures the only thing she actually cares about: whether there is a picture.

---

## 7. Open questions

1. Her real channel numbers. `config/commands.json` has names but every number
   is `null`, so `channel_set` correctly refuses everything.
2. Other IR devices in the room — AC, fan, sound system?
3. Is WiFi reliable at both the sofa and the TV cabinet?
4. Does she use the original remotes? If so, a permanently-wired IR *receiver*
   in the emitter becomes worth building — it would keep state in sync and log
   what she actually presses.
