# Handheld — Phase 3

The thing she holds. Press, speak, hear a Malayalam confirmation. Nothing else
to press.

```
wake on button
  -> beep         "I'm listening"      local, instant
  -> record to PSRAM, stop on silence
  -> beep         "got it"             local, instant
  -> POST the WAV to the backend
  -> play the reply                    Malayalam
  -> deep sleep
```

Board: **XIAO ESP32S3**, PSRAM verified at 8MB. Wiring in
[`docs/WIRING.md`](../../docs/WIRING.md).

## Setup

```bash
cp secrets.example.h secrets.h    # backend URL, device token, OTA password
```

Library Manager: **WiFiManager** (tzapu). Everything else ships with the core.

IDE settings:

| | |
|---|---|
| Board | XIAO_ESP32S3 |
| PSRAM | OPI PSRAM |
| USB CDC On Boot | Enabled |
| Partition Scheme | 8M with spiffs (3MB APP/1.5MB SPIFFS) — keeps OTA |

## It only records when the button wakes it

`setup()` runs on every boot — power-on, reset, and after every flash — not just
on a button press. Recording unconditionally meant a reconnected battery or a
power glitch would upload whatever the room happened to be saying, and once the
emitter exists that could switch her television on or off with nobody in the
room.

So it checks `esp_sleep_get_wakeup_cause()`. Only `ESP_SLEEP_WAKEUP_EXT0` — the
button — starts a recording. On a cold boot it plays a rising two-note chirp
("ready"), then sleeps armed. That doubles as useful feedback after charging.

**Holding the button through a cold boot overrides this**, which is how you
reach the WiFi portal and maintenance mode when standing next to it.

## The beeps

| Sound | Meaning |
|---|---|
| Rising two-note, 660→990Hz | Cold boot: ready and armed, going to sleep |
| Single 880Hz | Awake and listening |
| Single 1320Hz | Recording finished, working on it |
| Low two-tone, 400→300Hz | Something failed |
| Rising three-note | Maintenance mode, OTA open |

## The two beeps are not decoration

Measured round trip is ~3s and upload dominates, so no backend work brings the
spoken reply under about a second. The question she actually has is *"did it
hear me?"* — and a local beep answers that at zero latency.

Without it she repeats herself, and a repeated "TV on" toggles the television
back off. The beeps are the fix for the worst failure mode in the system. The
8-second debounce in the backend is the safety net behind them.

880Hz on wake, 1320Hz when the recording ends, and a low two-tone on any
failure. **Every failure path makes a sound** — silence is indistinguishable
from a dead device, and that is when she stops using it.

## Recording stops when she has finished

Whichever is latest: 1.2s of silence, or the button released. Minimum 0.7s,
hard cap 8s.

That tolerates both mental models. Holding it like a walkie-talkie works; so
does tapping and then speaking. She will use whichever feels natural without
being told which is correct.

The cap matters commercially as well as practically — Saaras is billed per
second of audio, and upload time dominates the round trip.

## Microphone gain

`MIC_GAIN_BITS` is the first thing to tune on real speech.

The INMP441 gives 24-bit data left-justified in a 32-bit frame. Shifting right
by 8 yields the true sample; another 8 makes it plain 16-bit. `MIC_GAIN_BITS`
adds gain on top, with **saturation**.

v1 used a bare `>> 8`, which crammed a 24-bit value into an `int16_t` and
wrapped around on anything above a whisper. That is why its audio was unusable.
Start at 2. Raise if her recordings are quiet, lower if loud speech clips.

## Maintenance mode

**Hold the button while it wakes.** After WiFi connects it stays awake for five
minutes with OTA listening, LED slow-blinking, and plays a rising three-tone.

This exists because the device lives hours away. Every other part of the design
was built so problems can be fixed without a car journey — the utterance log,
the WiFi captive portal, the cloud backend — and firmware is no exception. Once
this is soldered into a case, OTA is the only way in.

Upload target appears in the Arduino IDE as `revgen-remote` under network ports.

## Not yet compiled or run on hardware

Written against the board but never built. Expect to fix things.

The most likely trouble is the I2S API: this targets the legacy `driver/i2s.h`,
present in ESP32 core 2.x and still present but deprecated in 3.x. If your core
has removed it, migrate to `<ESP_I2S.h>` and the `I2SClass` wrapper — the logic
is unchanged, only the calls differ.

Bring up in the order in `docs/WIRING.md`: microphone alone first, then speaker
alone, then both. Wiring everything and flashing this tells you nothing about
which of six things is wrong.
