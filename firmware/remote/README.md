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

## Push to talk

**Hold the button, speak, let go.** Recording starts the instant it wakes —
there is no second press, and it does not wait for the network first. A 300ms
tail after release catches the last syllable, which people clip constantly by
letting go as they finish the word.

If the button is already up by the time recording starts — a quick tap, which
is what a short press looks like after ~300ms of boot — it falls back to
stopping on 1.2s of silence, so tap-and-speak still works.

Hard cap 6s either way. A stuck button should not upload six seconds of an
empty room repeatedly: Saaras is billed per second, and upload dominates the
round trip.

There is deliberately **no check that the button is still held at boot**. An
earlier version dismissed any press shorter than the ~300ms boot time as
spurious, which meant every normal press had to be made twice. The floating-pin
problem that check was guarding against is fixed properly at the source, by the
RTC pullup in `sleepNow()`.

## A second press cancels and starts over

Upload, download and playback together take about ten seconds. Locking her out
for all of it after a misspoken command is the kind of thing that makes a
device feel broken, so pressing the button again abandons the current attempt
and starts a fresh recording.

Every stage of the wait is interruptible, by one of two mechanisms:

| Stage | How |
|---|---|
| Upload (~7s) | button interrupt → `esp_restart()` |
| Download (~5s) | polled between reads |
| Playback (~3.5s) | polled between 2KB chunks |

**The upload reboots the device**, which sounds drastic and is the simplest
correct answer. `HTTPClient::POST` blocks for the entire request with no
callback to poll from — and it is the longest stage, so leaving it unresponsive
means most of the wait ignores her. Moving the network to its own FreeRTOS task
would work but brings shared state, teardown and a half-open TLS session to
clean up.

Nothing is worth preserving mid-upload: the recording is being abandoned by
definition, and the WiFi cache lives in RTC memory which survives a restart.
Boot back to a microphone is ~300ms, faster than the wait it replaces. An RTC
flag tells the next boot to skip straight to recording.

The interrupt is armed only around the blocking call, so playback keeps the
graceful chunked cancel rather than rebooting.

**Cancelling cannot un-fire IR.** If the backend already published to the
emitter, the television has already reacted — this skips the *wait*, not the
action. The backend's 8-second power debounce is what stops the resulting
second command undoing the first.

Detection is edge-triggered: the press that *ends* the recording is still
physically down when the upload begins, and would otherwise cancel itself
immediately. `armCancel()` requires the button to be seen released first.

## WiFi connects while she talks

The radio is kicked off *before* recording and waited on afterwards, so roughly
400ms of association disappears underneath two seconds of speech instead of
preceding it.

The channel, BSSID and leased IP are cached in RTC memory, which survives deep
sleep. That skips the all-channel scan and DHCP — about 1300ms down to under
400ms. It is only ever a cache: a moved router or an expired lease fails, falls
back to the full path, and refreshes itself. Three consecutive failures and the
cache is discarded.

## Loudness

She is hard of hearing, and a confirmation she cannot hear is the same as no
confirmation. Three independent levers, worth using all of them:

**Software — `BEEP_VOLUME` (0.85)** for the local tones, as a fraction of full
scale.

**Software — the spoken reply is normalised**, not scaled by a fixed amount.
Each clip is scanned for its loudest sample and lifted so that peak lands at
`PLAYBACK_PEAK`. Bulbul does not guarantee a consistent level between phrases,
so a fixed multiplier would either clip the loud ones or leave the quiet ones
inaudible. `MAX_NORMALISE_GAIN` caps it at 8x so a near-silent clip is not
amplified into hiss. The serial log prints `peak N -> gain N.NNx` so you can see
what each reply needed.

**Hardware — the MAX98357A `GAIN` pin**, which is free volume:

| GAIN connected to | Gain |
|---|---|
| VDD through 100kΩ | 3 dB |
| VDD | 6 dB |
| floating | 9 dB (default) |
| GND | 12 dB |
| GND through 100kΩ | **15 dB** |

Floating gives 9dB. A plain wire to GND gets you 12dB for nothing; 100kΩ to GND
gets 15dB and is the loudest the chip offers.

**Hardware — the speaker itself.** A 2W 40mm driver in a sealed printed
enclosure with a small port is dramatically louder than a bare driver flapping
on a breadboard. Do not judge final volume until it is mounted in the case.

If it is still not enough after all four, the honest answer is a bigger speaker
rather than more gain — past this point you are adding distortion, not volume.

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

### Uploading over WiFi

The Arduino IDE is supposed to show `revgen-remote` under **Network ports**, but
its mDNS discovery is unreliable on Windows even with the firewall opened. Skip
it and address the device directly:

```powershell
# Arduino IDE: Sketch > Export Compiled Binary  (Ctrl+Alt+S)
cd firmware\remote
.\ota_upload.ps1 -Ip 192.168.0.188 -Password <OTA_PASSWORD>
```

The script finds `espota` and the freshest `.bin` on its own, warns if the
binary is stale, and translates the usual failures.

If you do want discovery to work, it needs the network profile set to Private
plus inbound rules for UDP 5353, the IDE, and espota — all under the Private
profile. Even then it is flaky. The direct path always works.

## Reflashing over USB

Deep sleep powers down the XIAO's USB peripheral, so the COM port disappears
and the IDE has nothing to upload to.

**The firmware handles this itself now.** On a cold boot with a host holding
the serial port open, it stays awake for 15 seconds with the LED blinking fast
— plenty to hit Upload. On battery in her living room nothing has the port
open, so it sleeps immediately as intended.

Press RESET, then Upload while it is blinking.

**If it is already asleep**, force ROM download mode. The firmware does not run
at all in that state, so nothing can put it back to sleep:

1. Hold **B** (BOOT)
2. Press and release **R** (RESET)
3. Keep holding **B** another second, then release

Confirm it worked by the serial monitor showing *nothing* — no boot messages.
The COM port often changes number, so re-select it in Tools → Port before
uploading.

## Hardware verification status

The core remote operation has been compiled and verified on hardware. The carrier
PCB A2 has passed CAD checks; see `pcb/remote/A2_CORRECTIONS.md`. Charging components have not been tested on the
breadboard, and charging-related firmware behavior is still pending; first
charging tests are planned on the PCB prototype.

When changing ESP32 core versions, check the I2S API: this targets the legacy `driver/i2s.h`,
present in ESP32 core 2.x and still present but deprecated in 3.x. If your core
has removed it, migrate to `<ESP_I2S.h>` and the `I2SClass` wrapper — the logic
is unchanged, only the calls differ.

Bring up in the order in `docs/WIRING.md`: microphone alone first, then speaker
alone, then both. Wiring everything and flashing this tells you nothing about
which of six things is wrong.
