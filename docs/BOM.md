# Parts to buy

## Order this now — breadboard prototype only

Everything below is about getting the system *working*. Robustness comes after,
and most of this document belongs to that later stage.

Already in the parts box: IR receiver, IR LED, 100Ω + 1kΩ resistors,
microphone, tactile button, 3.7V cell, and an **ESP32-C3 Super Mini** (WiFi
verified, -39 dBm) which becomes the emitter. An ESP32-WROOM-32 is also on hand
as a spare.

### Buy now — ₹355

| Part | Qty | ~₹ |
|---|---|---|
| 2N2222A NPN transistor | 5 | 25 |
| Breadboard 830-point | 2 | 180 |
| Jumper wires M-M + M-F | 1 set | 150 |

That is the whole order. It covers Phase 0 and Phase 1 — IR codes recaptured
and a television controlled from a terminal — on boards already owned.

The C3 uses different pins to a classic ESP32 (onboard LED on GPIO8, active
low). `firmware/emitter/emitter.ino` handles both with
`#if CONFIG_IDF_TARGET_ESP32C3`, so no edits needed — just pick the right board
in the IDE.

### Buy later — only once Phase 1 works

The voice unit is Phase 3 for a reason: it is the component with the least
observable failures, and building it before the things it talks to exist is how
v1 died. Nothing below is needed to reach a working, TV-controlling system.

| Part | Qty | ~₹ |
|---|---|---|
| **Seeed XIAO ESP32S3** (plain, *not* Sense) | 1 | 1,200 |
| MAX98357A I2S amplifier | 1 | 250 |
| Speaker 8Ω 2W 40mm | 1 | 150 |

**Check the WROOM-32 first.** If the chip-info sketch reports 4–8MB of PSRAM it
is a WROVER, and it can serve as the voice unit — classic ESP32 has two I2S
ports, so mic-in and speaker-out both work. That would remove the XIAO from the
list entirely.

Deliberately not on this list yet: no battery (USB powers a breadboard), no
charging circuit, no RGB LED (both boards have one, and serial output is a
better debugger), no power switch, no enclosure, no PCB. None of it teaches you
anything about whether the idea works.

### Verify before relying on the parts you already have

Three of them fail silently if they're the wrong variant:

- **IR LED wavelength.** Must be **940nm**. 850nm LEDs look identical, glow
  faintly visible red when driven, and most receivers ignore them. If in doubt
  buy a few 940nm — they're ₹10.
- **Microphone type.** The design assumes a **digital I2S** mic (INMP441 or
  similar: pins marked SCK/WS/SD). An analog electret module (pins marked A0 or
  OUT) will not work without an ADC path and is far noisier — replace it rather
  than adapt to it.
- **IR receiver frequency.** TSOP**18**38 / 1738 / 4838 are all 38kHz and fine.
  A TSOP**12**40 or anything marked 40kHz will miss most of her remotes'
  signals.

Also check the **cell format**. If it's an 18650 rather than a flat LiPo pouch,
it still works but it is cylindrical and heavy, which changes the case design —
and the XIAO's onboard charger runs at a low current, so a large cell will take
most of a day to fill. Add a TP4056 if that becomes annoying. Confirm it has a
protection board and a JST-PH lead, not bare tabs.

---

Prices are approximate (Aug 2026, INR) and vary by seller — treat them as
"roughly what this should cost", not a quote. [Robu.in](https://robu.in),
[Probots](https://probots.co.in), [Hubtronics](https://hubtronics.in) and
Amazon.in all stock everything here.

Order everything in one go if you can — shipping is usually more annoying than
the parts. But if you're splitting it, **Group A alone gets you a system that
controls the TV from a terminal**, which is Phase 1.

---

## Group A — emitter + code capture (buy first)

This is the whole of Phase 0 and Phase 1. Cheap, and the voice unit depends on
nothing here being finished.

| Part | Qty | ~₹ | Notes |
|---|---|---|---|
| ESP32 DevKit v1 (ESP32-WROOM-32) | 2 | 350 ea | One becomes the emitter, one is your capture rig. Having both saves rewiring constantly. |
| **TSOP1838** IR receiver | 3 | 30 ea | 38kHz — matches both her remotes. Buy spares: they're 30 rupees and easy to kill with a reversed pin. |
| IR LED 940nm, 5mm | 6 | 10 ea | **940nm, not 850nm** — 850nm is for cameras and most receivers ignore it. Four in the emitter, two spare. |
| 2N2222A NPN transistor | 5 | 5 ea | Already proven in v1. |
| Resistor 100Ω ¼W | 10 | 1 ea | One per IR LED — see below. |
| Resistor 1kΩ ¼W | 10 | 1 ea | Transistor base. |
| Breadboard 830-point | 2 | 90 ea | |
| Jumper wires M-M / M-F | 1 set | 150 | |
| 5V 2A USB adapter + micro-USB cable | 1 | 250 | Mains power for the emitter. No battery — a stationary device with a battery is one that eventually dies without warning. |

**≈ ₹1,600**

### The one wiring detail that matters

Four IR LEDs in parallel, each with **its own 100Ω resistor**. LEDs don't
current-share; one shared resistor means one does nearly all the work and the
others barely light. Fan them across ~90° so aiming is designed out of the
system — she holds a microphone, not a pointer.

Start with **two** and test coverage from where the box will actually sit. IR
bounces off walls and ceilings better than people expect, and two may be enough
in a normal room. Add the others only if you find a dead angle.

Four LEDs at ~50mA each is ~200mA through the 2N2222A, comfortable against its
~600mA rating. Going beyond four buys little and starts warming the transistor.

---

## Group B — voice unit (Phase 3)

Build this last. By then everything it talks to already works, so it's the only
unknown in the system. v1 failed partly because this was built first.

**Plan: custom carrier PCB + 3D printed remote-shaped case.**

A board with everything soldered to it is *more* robust than modules hand-wired
into an off-the-shelf box — every joint on a PCB is a connection that cannot
work loose when it hits a tiled floor. And a remote-shaped object is one she
already knows how to hold, which is worth more than any spec here.

Because the PCB carries its own microphone, the **plain XIAO ESP32S3** is the
right module rather than the Sense. The Sense's selling point is its built-in
mic on a stacked expansion board; on a custom carrier that becomes redundant
height and cost.

| Part | Qty | ~₹ | Notes |
|---|---|---|---|
| **Seeed XIAO ESP32S3** (plain, not Sense) | 2 | 1,200 ea | ESP32-S3, **8MB PSRAM**, built-in LiPo charging. Buy two — one gets destroyed learning. |
| INMP441 I2S microphone | 2 | 200 ea | Goes on your PCB. Proven in v1. |
| MAX98357A I2S amplifier | 2 | 250 ea | |
| Speaker 8Ω **2W**, 40mm | 1 | 150 | Do not undersize. She is hard of hearing, and a confirmation she cannot hear is the same as no confirmation. |
| 3.7V LiPo 2000mAh | 1 | 450 | Check the connector — XIAO uses JST-PH 2-pin. |
| Tactile button, **12mm+** | 5 | 20 ea | The most important physical part in the project. Order a few types and let her pick before you finalise the footprint. |
| RGB LED (common cathode) | 3 | 10 ea | Status that works even when audio fails. |
| Slide switch | 2 | 15 ea | |
| **PCB fab** (JLCPCB/PCBWay, 5 boards) | 1 | 1,500–2,500 | Boards are ~₹200; shipping to India dominates. Order 5, you get 5. |
| Heat-set threaded inserts M3 | 20 | 5 ea | Not self-tapping screws. The case will be opened repeatedly. |
| PETG or ASA filament | 1 | 1,200 | **Not PLA** — see below. |
| TPU filament (grip sleeve) | 1 | 1,400 | Optional but this is what replaces the soft overmould. |
| Magnetic USB-C charging tip + cable | 1 | 300 | So she never has to aim a connector. |
| Lanyard / wrist strap | 1 | 80 | It will be dropped. |

**≈ ₹6,500** including filament you'll reuse for years. Excluding filament,
roughly ₹4,000.

### Why this module

Checked Aug 2026 against the alternatives. Three routes were considered:

| Route | ~₹ | Verdict |
|---|---|---|
| ESP32-S3-DevKitC-1 N16R8 + INMP441 + TP4056 | 1,060 | Cheapest, but a 55×26mm board with three breakouts wired around it constrains the case shape. |
| XIAO ESP32S3 **Sense** + amp | 2,200 | Mic built in — but it lives on a stacked expansion board, which is redundant height and cost once your own PCB carries an INMP441. |
| **XIAO ESP32S3 (plain) on a custom carrier** | 1,200 | Chosen. PSRAM and battery charging on a 21×17.5mm module, everything else on your board. |

The deciding factor is that a custom PCB changes the maths. The Sense only wins
when you are not making a board — its selling point is the integrated
microphone, and you are placing your own. The DevKitC only wins on price, and it
dictates the case dimensions you specifically want to control.

**Against the XIAO:** 11 usable GPIOs (enough here — I2S in, I2S out, button,
LED), and castellated pads mean soldering rather than breadboarding. Buy two so
the first mistake is not also the last.

### Not worth switching to

**ESP32-P4** is the newest and much faster, but it has **no WiFi or Bluetooth**
— it needs a companion radio chip. That's a non-starter for a device whose
entire job is uploading audio.

**ESP32-C6 / C5** are newer RISC-V parts aimed at low-power and Thread/Matter.
No PSRAM, weaker on audio. A step sideways at best.

The ESP32-S3 is still the right chip for this in 2026.

### PCB design

**Carrier board, not a bare ESP32-S3.** Keep the XIAO as a module soldered onto
your board via its castellated pads. Designing a bare S3 with USB, power
management and antenna matching is a lot of ways for a first PCB to fail, and a
carrier means a mistake costs a reroute rather than a dead board. It also means
the module is replaceable if she drops it hard enough to crack something.

**EasyEDA** if this is your first board — it's free and orders straight from
JLCPCB with the footprints already in their library. KiCad if you want the
skill to transfer.

On the board: XIAO footprint, INMP441, MAX98357A, button, RGB LED, JST-PH
battery connector, speaker pads.

Things that catch people out:

- The **INMP441 must be well away from the speaker** and ideally on the opposite
  end of the board, or it hears the confirmation and the amplifier's switching
  noise. Physical distance is the fix; there is no software one.
- Put a **ground pour** under the digital section and keep the I2S clock lines
  short.
- Add **test pads** on I2S clock/data, the button line and battery voltage. You
  will want them at 11pm when it doesn't boot.
- Give the button a **generous footprint** and pick the switch *before* routing
  — you want her to try a few and choose one by feel.
- Order **5 boards**. They cost almost nothing; shipping is the expense.

Budget 2–3 weeks per revision including shipping to India, and expect two
revisions. Start the board early even though the firmware comes last.

### 3D printed case

Aim for a familiar TV-remote silhouette, but chunkier: roughly **160 × 60 ×
28mm**. Long enough not to vanish down the side of a chair, thick enough to
grip in the palm rather than pinch between fingertips — pinching is what
arthritis makes hard.

**Print in PETG or ASA. Not PLA.** PLA is brittle on impact and creeps in heat;
a remote left on a sunny windowsill in Kerala will soften and warp. PETG has far
better layer adhesion and survives drops.

- **Walls ≥ 2.4mm**, and orient the print so layer lines run *across* the case
  rather than along it. Layer adhesion is the weak axis and drops load the
  corners.
- **Print a TPU sleeve** to slip over the body. That is what replaces the soft
  overmould on a commercial enclosure, and it does the same two jobs: grip for
  unsteady hands, and impact absorption at the corners.
- **Heat-set M3 inserts**, not screws driven into plastic. You will open this
  many times and self-tapping screws strip out after a few.
- **Retain the LiPo** with a printed bracket or foam. A cell rattling loose
  inside a dropped case is a puncture risk.
- Round every external corner generously. Sharp printed edges feel cheap and
  concentrate impact.

**Layout:**

- Battery at the bottom end so it is weighted like a torch and stands rather
  than tips. Target around 200g — solid without being tiring.
- One large button, centred, about a third down from the top where the thumb
  naturally rests. Nothing else she can press.
- Speaker firing out the **front face**, never the back. A speaker pointed into
  her palm or her lap produces a confirmation she cannot hear, which defeats the
  entire latency design.
- Microphone port on the **top edge**, away from where fingers wrap.
- Lanyard anchor at the bottom.

**Charging: a magnetic USB-C tip** left in the port permanently. She brings the
cable near and it snaps on — no aiming a connector, and the USB port is the
most mechanically fragile thing on the device. With 2000mAh and deep sleep this
is weekly, not daily.

### Fallback if the PCB slips

A **Hammond 1553D** (147 × 89 × 25mm, soft overmoulded ABS, IP54, ~₹1,200 from
[element14 India](https://in.element14.com/c/enclosures-racks-cabinets/enclosures-boxes-cases?brand=hammond)
or [RS India](https://in.rsdelivers.com/product/hammond/1553dgy/hammond-1553-series-grey-abs-handheld-enclosure-mm/5135319))
with modules on perfboard gets a working unit into her hands while the boards
are in transit. Worth knowing it exists; not worth buying up front.

### Whatever you buy, it must have PSRAM

This is the single most important spec in the project, and it is the direct
fix for why v1 died. The old firmware streamed raw audio to OpenAI over a TLS
WebSocket because it could not hold a recording in memory. With PSRAM,
buffering 6 seconds of 16kHz WAV (~192KB) is trivial and the whole
record-then-upload design becomes easy.

The XIAO ESP32S3 has 8MB PSRAM in both the plain and Sense versions, so either
satisfies this. The plain one is correct here because your PCB carries the
microphone.

If you fall back to a DevKitC instead, it must say **N16R8** or **N8R8**. A
plain N8 or N16 with no `R` has no PSRAM, and many listings sold as "ESP32-S3"
never mention it.

---

## Group C — worth having, not required

| Part | Qty | ~₹ | Notes |
|---|---|---|---|
| Project enclosure, ~100×60×25mm | 2 | 150 ea | One per device. Hers should be comfortable to hold. |
| Perfboard / zero PCB | 3 | 40 ea | For moving off breadboard once it works. |
| Soldering iron + solder | 1 | 800 | If you don't already have one. |
| Multimeter | 1 | 600 | You will want this the first time an IR code doesn't fire. |
| USB-to-TTL (CP2102) | 1 | 200 | Only if you go custom PCB later. |

---

## Totals

| | ≈ ₹ |
|---|---|
| Group A — gets the TV working from a terminal | 1,600 |
| Group B — the handheld (incl. filament + PCB fab) | 6,500 |
| **Both** | **8,100** |

Plus roughly ₹55/month in Sarvam API costs, and ₹100 of free signup credits
already covering the first couple of months.

---

## What to do the day Group A arrives

1. Wire the TSOP1838 to the spare ESP32 and recapture **every button on both
   remotes**. `stb.digit_1` in the current catalogue is byte-identical to
   `channel_down` — a copy-paste bug from v1 — so any channel containing a 1 is
   refused until this is done.
2. While the receiver is set up, **sweep the Panasonic command space** (address
   `0x8`, commands `0x00`–`0xFF`) with a camera pointed at the TV. Manufacturers
   usually ship discrete power-on and power-off codes that aren't on the
   physical remote. If hers has them, fill them into the `discrete` block in
   `config/commands.json` and the resolver stops using toggles by itself — the
   whole repeat-and-toggle-it-back-off problem disappears.
3. Flash `firmware/emitter/emitter.ino`, set the broker credentials, and fire a
   test with `mosquitto_pub`. That's Phase 1 complete.
