# Emitter circuit recovered from v1

**Update:** the original Gerbers have now been supplied. Their routing differs
from this PDF: see [Gerber recovery](EMITTER_GERBER_RECOVERY.md), which takes
precedence for the actual PCB. Header spacing is recovered; no ruler measurement
is needed to reproduce the original hole pattern. Findings below refer to the PDF.

Reviewed 2026-09-08. Source: `docs/revgen-transmitter.pdf`, revision 1.0,
2025-04-11, and `docs/assets/ESP32-Pinout(Transmitter).jpg.webp`.
Historical firmware: commit `4476c95`, `transmitter/transmitter.ino`,
and commit `fdbe8bb`, `firmware/emitter/emitter.ino`.

The user confirms this is the board/circuit previously used to control the TV,
with one physical wiring mistake. The PDF is a schematic, not PCB copper;
it cannot establish what was actually soldered or which trace was mistaken.
No editable emitter PCB or Gerber archive was found in the available Git history.

## Correct board reference

The original schematic and pinout image show a **30-pin development board**,
15 pins per side. The newly supplied NodeMCU-32S 38-pin PDFs are explicitly
rejected by the user as the wrong hardware. Do not use the footprint generated
from those PDFs. The old image establishes pin order but has no dimensioned
header spacing; do not infer an order-ready footprint from its aspect ratio.

With antenna up and USB down, component side visible:

| Row position from top | Left | Right |
|---:|---|---|
| 1 | EN | GPIO23 |
| 2 | GPIO36 / VP | GPIO22 |
| 3 | GPIO39 / VN | GPIO1 / TX0 |
| 4 | GPIO34 | GPIO3 / RX0 |
| 5 | GPIO35 | GPIO21 |
| 6 | GPIO32 | GPIO19 |
| 7 | GPIO33 | GPIO18 |
| 8 | GPIO25 | GPIO5 |
| 9 | GPIO26 | GPIO17 |
| 10 | GPIO27 | GPIO16 |
| 11 | GPIO14 | GPIO4 |
| 12 | GPIO12 | GPIO2 |
| 13 | GPIO13 | GPIO15 |
| 14 | GND | GND |
| 15 | VIN | 3V3 |

These are row positions, not bare-module pad numbers.

## Findings in the saved schematic

1. **LED U3 is reversed as drawn.** Its cathode bar faces R6/VIN;
   its anode faces Q2 collector. Correct current path is positive supply,
   resistor, LED anode, LED cathode, transistor collector, emitter, ground.
   A working assembled unit must differ from this drawing here, or its original
   symbol/footprint mapping differed. This is not proof of the user's physical fault.
2. **R3 pulls receiver OUT/GPIO13 to VIN (nominal USB 5 V).** ESP32
   signals must stay at 3.3 V logic. A receiver powered at 5 V may also source
   a high output itself; merely changing the external pull-up is insufficient
   without checking the exact receiver.
3. **C1, 100 nF, is across OUT and GND**, not receiver supply and ground.
   With R3=10 kohm it gives a 1 ms RC time constant that can distort decoded
   IR pulses. Move decoupling to receiver VS–GND.
4. **R4 pulls GPIO12/button to VIN.** Besides the 5 V logic problem,
   GPIO12 is a flash-voltage boot strap. A high level at reset can select
   1.8 V and prevent a 3.3 V flash board from booting. Move an optional user
   button to GPIO27, switch to GND, pull up to 3V3.
5. **Old IR firmware and schematic agree on GPIO5.** Current flashed firmware
   uses GPIO4. Reusing the old PCB unchanged with current firmware requires
   rerouting the base-resistor input from GPIO5 to GPIO4, or deliberately
   rebuilding firmware for GPIO5. This mismatch is not evidence that the
   original PCB had a GPIO error when running its original firmware.
6. **Q2 has no base-to-emitter pull-down.** Add 10 kohm so the driver is off
   while the MCU output is high impedance.
7. J1 is labelled "Speaker port", but carries VIN, GND and GPIO27. It is not
   an amplified speaker output. Omit it from the emitter carrier unless its
   original accessory is explicitly needed; never connect a bare speaker
   directly to this GPIO.

## Revised circuit specification

Preserve the original single-LED transistor driver, with conservative original
resistor values. Do not replace it with the later four-LED/100-ohm example.

- Existing ESP32 board powered through its USB connector.
- VIN/USB-derived 5 V -> R_LED 330 ohm, 0.25 W -> IR LED anode.
- IR LED cathode -> Q1 collector; Q1 emitter -> GND.
- GPIO4 -> R_BASE 1 kohm -> Q1 base. R_OFF 10 kohm from base to emitter/GND.
- Q1 design reference: onsemi **P2N2222A**, pins 1=C, 2=B, 3=E per its
  datasheet. Generic PN2222A/2N2222A substitutions can have different lead
  order: final footprint must match the owned part, not just the name "2222".
- Original LED reference: IR333C/H0-A. Retain 330 ohm pending exact variant
  verification. At an illustrative 5 V supply, 1.3 V LED drop and 0.2 V
  transistor drop, current is approximately 10.6 mA and resistor power 37 mW.
  This is a design estimate, not a measured range/current result.
- Add 100 nF ceramic and 47 uF / 10 V bulk capacitance across the driver supply,
  close to the driver. Keep pulsed LED current return separate from receiver
  signal wiring until the ground plane connection.
- Add labelled test points: VIN, GND, GPIO4 and collector.
- Optional button: GPIO27 -> switch -> GND, with 10 kohm to 3V3. Current
  production firmware does not implement this button; it is an optional
  expansion, not a working control until supported in firmware.
- Receiver is optional for capture, not required for MQTT emission. Provide
  a clearly labelled 3V3/GND/OUT header with OUT -> GPIO15 to match the current
  capture sketch. Only connect a receiver explicitly rated for 3.3 V supply
  and logic. Put 100 nF across its supply at the receiver. The old generic
  TSOP1838 designation does not establish its manufacturer or voltage limits;
  a 5 V-only receiver needs its own checked supply and output level conversion.

The revised GPIO4 choice matches the firmware already flashed and tested.
No board was reflashed or physically rewired during this review.

## Release status

Circuit corrections specified; PCB layout not released. Recover the original
EasyEDA layout or measure header spacing and body dimensions before routing a
replacement. Verify diode and transistor pad polarity against actual parts.
Then generate a readable native schematic, route the carrier, and run ERC,
DRC and schematic/PCB net parity before producing Gerbers.

References:
- [ESP32 boot straps](https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/boot-mode-selection.html)
- [onsemi P2N2222A datasheet](https://www.onsemi.com/pdf/datasheet/p2n2222a-d.pdf)
