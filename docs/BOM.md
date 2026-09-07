# Parts

Prices are approximate (Aug 2026, INR) and vary by seller — treat them as
"roughly what this should cost", not a quote. [Robu.in](https://robu.in),
[Robocraze](https://robocraze.com), [Probots](https://probots.co.in),
[Hubtronics](https://hubtronics.in) and Amazon.in stock everything here.

## Already owned

IR receiver, IR LED, 100Ω + 1kΩ resistors, digital microphone, tactile button,
3.7V cell.

Boards on hand:

| Board | PSRAM | Role |
|---|---|---|
| ESP32-C3 Super Mini | none | Previously recorded emitter choice; historical WiFi result −39 dBm |
| **Classic ESP32 (D0WD-V3, 4MB flash)** | none — previously confirmed 0 bytes | **Current emitter**, chip and flash identified over USB on 2026-09-08 |

The WROOM-32 was checked for PSRAM in case it was a WROVER, which would have
served as the voice unit and removed the XIAO from the list. It reported 0, so
that shortcut is out.

The connected emitter was identified as ESP32-D0WD-V3 revision 3.1 through a
CP2104 USB bridge on COM8. Both boards can handle the emitter workload; PSRAM
is not required. Use **ESP32 Dev Module**, 4 MB flash, PSRAM disabled for the
current classic board. IR drive remains GPIO4; status LED is GPIO2 if fitted.

The C3 uses different pins to a classic ESP32 (onboard LED on GPIO8, active
low). `firmware/emitter/emitter.ino` handles both with
`#if CONFIG_IDF_TARGET_ESP32C3` — no edits needed, just pick the right board in
the IDE, and enable **USB CDC On Boot** or the C3 gives no serial output.

## Ordered — ₹355

Everything needed to finish Phase 0 and Phase 1 on boards already owned: IR
codes recaptured, and a television controlled from a terminal.

| Part | Qty | ~₹ |
|---|---|---|
| 2N2222A NPN transistor | 5 | 25 |
| Breadboard 830-point | 2 | 180 |
| Jumper wires M-M + M-F | 1 set | 150 |

## Buy later — voice unit, ~₹1,600

Phase 3, and not before. It is the component with the least observable
failures, and building it before the things it talks to exist is how v1 died.
Nothing here is needed to reach a working, TV-controlling system.

| Part | Qty | ~₹ |
|---|---|---|
| **Seeed XIAO ESP32S3** (plain, *not* Sense) | 1 | 1,200 |
| MAX98357A I2S amplifier | 1 | 250 |
| Speaker 8Ω **2W** 40mm | 1 | 150 |

Deliberately absent: battery and charging (USB powers a breadboard), RGB LED
(both boards have one, and serial is a better debugger), power switch,
enclosure, PCB. None of it teaches you whether the idea works.

## Verify before relying on the parts already in the box

Three fail silently if they are the wrong variant:

- **IR LED wavelength — must be 940nm.** 850nm LEDs look identical, glow
  faintly visible red when driven, and most receivers ignore them. Point a
  phone camera at it while firing: both show up on camera, but a dull red glow
  visible to the naked eye means 850nm.
- **Microphone must be digital I2S** — pins marked SCK/WS/SD, like an INMP441.
  An analog electret module (pins marked A0 or OUT) will not work with this
  firmware and is far noisier. Replace rather than adapt.
- **IR receiver must be 38kHz.** TSOP**18**38 / 1738 / 4838 are all fine. A
  TSOP**12**40 or anything marked 40kHz will miss most of her remotes.

Also check the **cell**: confirm it has a protection board and a JST-PH lead
rather than bare tabs. If it is an 18650 rather than a flat pouch it still
works, but it is cylindrical and heavy, which affects the case, and the XIAO's
onboard charger is low-current so a large cell takes most of a day to fill.

---

# Later: the finished device

Everything below is for after the breadboard prototype works. None of it is
urgent, and some of it will change once there is something real to hold.

## Why the XIAO ESP32S3

Three routes were considered in Aug 2026:

| Route | ~₹ | Verdict |
|---|---|---|
| ESP32-S3-DevKitC-1 N16R8 + INMP441 + TP4056 | 1,060 | Cheapest, but a wide board that covers most of a breadboard and dictates the case dimensions. |
| XIAO ESP32S3 **Sense** + amp | 2,200 | Mic built in — but on a stacked expansion board, which is redundant height and cost once your own PCB carries an INMP441. |
| **XIAO ESP32S3 (plain)** | 1,200 | Chosen. PSRAM and LiPo charging on a 21×17.5mm module. |

The Sense only wins when you are *not* making a PCB. Its selling point is the
integrated microphone, and this design places its own.

**Against the XIAO:** 11 usable GPIOs (enough — I2S in, I2S out, button, LED),
and castellated pads mean soldering rather than pushing into a breadboard. It
needs the little IPEX antenna from the box plugged in, and **USB CDC On Boot**
enabled in the IDE.

### Whatever the board, it must have PSRAM

The single most important spec in the project, and the direct fix for why v1
died. The old firmware streamed raw audio over a TLS WebSocket because it could
not hold a recording in memory. With PSRAM, buffering 6 seconds of 16kHz WAV
(~192KB) is trivial and record-then-upload becomes easy.

The XIAO ESP32S3 has 8MB in both plain and Sense variants. If falling back to a
DevKitC it must say **N16R8** or **N8R8** — a plain N8 or N16 with no `R` has
none, and listings often do not mention it.

### Not worth switching to

**ESP32-P4** is newer and much faster but has **no WiFi or Bluetooth** — a
non-starter for a device whose entire job is uploading audio.

**ESP32-C3 / C6 / C5** have no PSRAM. The C3 is a fine *emitter* — that is what
this project uses one for — but 400KB of SRAM cannot hold a recording alongside
a TLS connection, which is exactly the corner v1 painted itself into.

The ESP32-S3 remains the right chip for the handheld in 2026.

## PCB

**Carrier board, not a bare ESP32-S3.** Keep the XIAO as a module soldered onto
castellated pads. Designing a bare S3 with USB, power management and antenna
matching is a lot of ways for a first board to fail; a carrier means a mistake
costs a reroute rather than a dead board, and the module stays replaceable.

**EasyEDA** if this is your first board — free, and orders straight from JLCPCB
with footprints already in their library. KiCad if you want the skill to
transfer.

On the board: XIAO footprint, INMP441, MAX98357A, button, RGB LED, JST-PH
battery connector, speaker pads.

Things that catch people out:

- **Put the INMP441 at the opposite end from the speaker**, or it picks up the
  confirmation audio and the amplifier's switching noise. Physical distance is
  the fix; there is no software one.
- Ground pour under the digital section, and keep the I2S clock lines short.
- **Test pads** on I2S clock/data, the button line and battery voltage. You will
  want them at 11pm when it does not boot.
- **Pick the button before routing.** Order several types, let her press them,
  then commit the footprint. It is the one part she physically interacts with.
- Order 5 boards. They cost almost nothing; shipping is the expense.

Budget 2–3 weeks per revision including shipping to India, and expect two. Worth
starting early even though the firmware is Phase 3, since that lead time runs in
parallel.

## Case

A familiar TV-remote silhouette but chunkier — roughly **160 × 60 × 28mm**. Long
enough not to vanish down the side of a chair, thick enough to grip in the palm
rather than pinch between fingertips. Pinching is what arthritis makes hard.

**Print in PETG or ASA, not PLA.** PLA is brittle on impact and creeps in heat;
a remote left on a sunny windowsill in Kerala will soften and warp.

- **Walls ≥ 2.4mm**, and orient the print so layer lines run *across* the case.
  Layer adhesion is the weak axis and drops load the corners.
- **Print a TPU sleeve** to slip over the body. That is what replaces the soft
  overmould on a commercial enclosure: grip for unsteady hands, and corner
  impact absorption.
- **Heat-set M3 inserts**, not screws driven into plastic. You will open this
  many times and self-tapping screws strip out.
- **Retain the cell** with a printed bracket or foam. One rattling loose inside a
  dropped case is a puncture risk.
- Round every external corner generously.

**Layout:**

- Battery at the bottom so it is weighted like a torch and stands rather than
  tips. Target around 200g — solid without being tiring.
- One large button, centred, about a third down from the top where the thumb
  naturally rests. Nothing else she can press.
- Speaker firing out the **front face**, never the back. A speaker pointed into
  her palm or her lap is a confirmation she cannot hear, which defeats the whole
  latency design.
- Microphone port on the **top edge**, away from where fingers wrap.
- Lanyard anchor at the bottom.

**Charging: a magnetic USB-C tip** left in the port permanently, so she never
aims a connector — the USB port is the most mechanically fragile part of the
device. With 2000mAh and deep sleep this is weekly, not daily.

### Fallback if the PCB slips

A **Hammond 1553D** (147 × 89 × 25mm, soft overmoulded ABS, IP54, ~₹1,200 from
[element14 India](https://in.element14.com/c/enclosures-racks-cabinets/enclosures-boxes-cases?brand=hammond)
or [RS India](https://in.rsdelivers.com/product/hammond/1553dgy/hammond-1553-series-grey-abs-handheld-enclosure-mm/5135319))
with modules on perfboard puts a working unit in her hands while boards are in
transit. Worth knowing it exists; not worth buying up front.

## Rough cost of the finished device

| | ≈ ₹ |
|---|---|
| Electronics (already owned + ₹355 + ₹1,600) | 1,955 |
| PCB fab, 5 boards incl. shipping | 1,500–2,500 |
| Filament (PETG + TPU, reusable for years) | 2,600 |
| Inserts, magnetic cable, lanyard | 400 |

## The day the parts arrive

1. Wire the TSOP1838 to an ESP32 and **recapture every button on both remotes**.
   `stb.digit_1` is byte-identical to `channel_down` — a copy-paste bug from v1 —
   so any channel containing a 1 is refused until this is fixed.
2. While the receiver is set up, **sweep the Panasonic command space** (address
   `0x8`, commands `0x00`–`0xFF`) with a camera pointed at the TV. Manufacturers
   usually ship discrete power-on/off codes that are not on the remote. Fill
   them into the `discrete` block in `config/commands.json` and the resolver
   stops using toggles by itself — the repeat-and-turn-it-back-off problem
   disappears.
3. Flash `firmware/emitter/emitter.ino`, fill in `secrets.h`, and fire a test.
   That is Phase 1 complete.
