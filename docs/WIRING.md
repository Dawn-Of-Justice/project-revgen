# Wiring and pin assignment

Enough to breadboard both devices. This is the input to a schematic later — get
it working here first, then draw the circuit you actually proved.

Pin numbers below match what is already in the firmware. Change them here and
in the sketch together, or nothing works and it looks like a hardware fault.

---

## Emitter — ESP32-C3 Super Mini

| Signal | GPIO | Goes to |
|---|---|---|
| IR drive | **4** | 1kΩ → base of 2N2222A |
| Status LED | **8** | onboard LED, active low — nothing to wire |
| IR receive *(capture sketch only)* | **3** | TSOP1838 OUT |

### IR driver

The 2N2222A has exactly three legs, and all three are used: base from the GPIO,
collector to the LEDs, emitter to ground.

```
                          5V
                           │
          ┌────────┬───────┴───────┬────────┐
        [100R]   [100R]         [100R]   [100R]
          │        │               │        │
         LED      LED             LED      LED       (940nm, cathode down)
          │        │               │        │
          └────────┴───────┬───────┴────────┘
                           │
                     COLLECTOR (C)
                           │
GPIO4 ──[1k]──── BASE (B) ─┤  2N2222A
                           │
                      EMITTER (E)
                           │
                          GND
```

The transistor is just a switch. GPIO4 drives the base through the 1kΩ; that
turns the transistor on, which connects the LED cathodes to ground and lights
them. The ESP32 pin only ever carries ~2.6mA — the 140mA for the LEDs comes from
the 5V rail through the collector, which is the entire reason for the transistor.
A GPIO cannot source that directly.

**One resistor per LED.** LEDs do not current-share — a single shared resistor
leaves one doing nearly all the work while the others barely light.

Start with **two** LEDs and test coverage from where the box will actually sit.
IR bounces off walls and ceilings better than people expect. Add the others only
if you find a dead angle.

The numbers: ~1.3V forward drop, so each LED pulls about 35mA through its 100Ω
from the 5V rail. Four is ~140mA. Base current is (3.3−0.7)/1k ≈ 2.6mA, which
at hFE≈100 supports well over that. Comfortable against the 2N2222A's ~600mA
rating. Going beyond four buys little and starts warming the transistor.

**The 5V pin is only live when USB is plugged in.** That is fine — the emitter
is mains powered by design. No battery: a stationary device with a battery is
one that eventually dies without warning.

### Capture rig

Three wires, no transistor or LED needed:

| TSOP1838 | to |
|---|---|
| OUT | GPIO3 |
| VCC | 3V3 |
| GND | GND |

TSOP pin order varies by package — check the datasheet before powering it.
Reversing VCC and GND kills them instantly, which is why the BOM says buy three.

---

## Voice unit — XIAO ESP32S3

XIAO silkscreen labels (D0–D10) do not match GPIO numbers. Both are given
because the silkscreen is what you see while wiring and the GPIO number is what
goes in the code.

| Signal | Pad | GPIO | Goes to |
|---|---|---|---|
| Mic bit clock | D8 | **7** | INMP441 SCK |
| Mic word select | D9 | **8** | INMP441 WS |
| Mic data | D10 | **9** | INMP441 SD |
| Amp bit clock | D0 | **1** | MAX98357A BCLK |
| Amp word select | D1 | **2** | MAX98357A LRC |
| Amp data | D2 | **3** | MAX98357A DIN |
| Button | D3 | **4** | button → GND, `INPUT_PULLUP` |
| Status LED | — | **21** | onboard, active low |

**Plus power and ground to both modules** — those are not GPIO so they are not
in the table above, and forgetting them is an easy way to spend an evening
debugging a module that was never switched on:

| | INMP441 | MAX98357A |
|---|---|---|
| Power | 3V3 | 5V on the breadboard, **BAT+** once on battery |
| Ground | GND | GND |

The ESP32-S3 has two I2S peripherals, so the microphone runs on `I2S_NUM_0` and
the amplifier on `I2S_NUM_1` — no reconfiguring between record and playback.
(This is one of the reasons a C3 could not do this job.)

### INMP441

| Pin | to |
|---|---|
| VDD | 3V3 |
| GND | GND |
| L/R | **GND** — selects the left channel, which the firmware reads |
| SCK / WS / SD | GPIO7 / 8 / 9 |

Leaving L/R floating gives silence on the channel you are reading, which looks
exactly like a dead microphone.

### MAX98357A

| Pin | to |
|---|---|
| VIN | **5V** while breadboarding; **BAT+** in the final build — see below |
| GND | GND |
| BCLK / LRC / DIN | GPIO1 / 2 / 3 |
| GAIN | leave floating for 9dB; tie to GND for 12dB |
| SD | leave alone — the breakout pulls it up. Pulling it low mutes the amp. |
| + / − | speaker |

**On the breadboard, use the 5V pin.** It is live whenever USB is plugged in,
and there is no battery yet, so BAT+ is dead.

**In the final build, move it to BAT+ — not 3V3.** XIAO's 5V pin goes dead on
battery power, so the amp would fall back to 3.3V and get noticeably quieter.
Wired to BAT+ it sees 3.7–4.2V, which matters because she is hard of hearing and
a confirmation she cannot hear is the same as no confirmation. The MAX98357A
accepts 2.5–5.5V with good supply rejection, so the sagging battery voltage is
fine.

If it is still too quiet, tie GAIN to GND before reaching for a bigger speaker.

### Button

To GND with `INPUT_PULLUP` — no external resistor. Debounce in software.

Avoid D6/D7 (GPIO43/44): they are the UART, and you want serial output while
debugging this.

---

## Bring-up order

Test each piece alone. Wiring everything then powering on gives you no idea
which of six things is wrong.

1. **`firmware/selftest`.** USB only, no wiring. Confirms the board, the IDE
   settings, the PSRAM (including a real 192KB allocation) and surveys WiFi.
   Enable **USB CDC On Boot**, and on a XIAO set **Tools > PSRAM = OPI PSRAM**
   or a board that has 8MB reports zero.
2. **Re-run the scan from where the device will actually sit.** Behind a
   cabinet is a different number from your desk, and anything worse than about
   -70 dBm means intermittent MQTT drops later.
3. **TSOP alone**, with `firmware/capture`. Press any remote and watch codes
   appear. This is Phase 0 and needs nothing else.
4. **IR LED alone.** Fire one code at the TV. A phone camera sees IR — point it
   at the LED to confirm it is flashing before blaming the code.
5. **Emitter on MQTT.** `firmware/emitter` with `secrets.h` filled in. Watch
   `/health` flip `emitter_online` to true. That is Phase 1.
6. **Microphone alone.** Record and dump levels over serial before involving
   the network.
7. **Speaker alone.** Play a tone before involving the microphone.
8. **Both together** — and listen for the amplifier's switching noise in the
   recording. If it is there, physical distance between mic and speaker is the
   only fix, and it is why they go at opposite ends of the eventual PCB.

## Things that quietly waste an evening

**2N2222A pinout.** TO-92, flat face toward you, legs down: **E–B–C** left to
right. Verify against the datasheet for your specific part — some suppliers ship
PN2222A or S8050 with different orders, and a swapped transistor simply does
nothing while looking correctly wired.

**IR LED polarity.** Long leg is the anode, toward the 100Ω and 5V. Backwards is
silent, not broken.

**IR LED wavelength.** Must be 940nm. 850nm looks identical and glows faintly
visible red when driven, and most receivers ignore it entirely.

**C3 strapping pins.** GPIO2, GPIO8 and GPIO9 are read at boot. GPIO8 as the
status LED is normal (it is the onboard LED), but do not hang anything that
pulls GPIO9 low or the board enters download mode instead of running.

**Common ground.** Everything shares GND, including the transistor emitter. This
is the single most common breadboard mistake and it produces symptoms that look
like software bugs.
