# Handheld carrier PCB

Everything on this board is already proven on the breadboard. This is
transcription plus four deliberate changes, all of which came out of testing:

| Change | Why |
|---|---|
| `SD` on GPIO5 instead of tied high | Amp draws 2.4mA when enabled — 35x the rest of the sleeping device. This is what decides how often she charges it. |
| `GAIN` to GND | 12dB instead of the floating 9dB. Free volume, and it repays the headroom given up to stop clipping. |
| Mic at the opposite end from the speaker | It hears the confirmation otherwise, and there is no software fix. |
| Test points on I2S, button, battery | You will want them at 11pm when it does not boot. |

## Approach: carrier, not a bare ESP32-S3

The XIAO is soldered onto this board as a module. Designing a bare ESP32-S3
means USB, power management, and antenna matching — a lot of ways for a first
board to fail, and a respin costs 2–3 weeks to India. A carrier means a mistake
costs a reroute, and the expensive part stays replaceable.

Same logic for the INMP441 and MAX98357A: use the breakout modules. The bare
parts are a bottom-ported MEMS and a TQFN, neither hand-solderable without
reflow. Solder the modules **flat, without headers** — headers add ~8mm of
height for nothing.

## Components

| Ref | Part | Footprint | Notes |
|---|---|---|---|
| U1 | Seeed XIAO ESP32S3 | 21 × 17.5mm, 2×7 castellated, 2.54mm pitch | Already in the JLCPCB/EasyEDA library |
| U2 | INMP441 module | 6-pin header, 2.54mm | Place at the far end from U3 |
| U3 | MAX98357A module | 7-pin + 2 speaker pads | |
| SW1 | Tactile switch, 12mm | 4-pin THT | Pick the actual switch before routing |
| J1 | JST-PH 2.0, 2-pin | THT right-angle | Battery |
| J2 | JST-PH 2.0, 2-pin | THT | Speaker |
| SW2 | SPDT slide switch | THT | Battery isolation — see below |
| C1,C3 | 10µF ceramic | 0805 | Bulk, one per module |
| C2,C4 | 100nF ceramic | 0805 | Decoupling, one per module |
| C5 | 220µF electrolytic | THT, 6.3mm | Across the amp supply — see below |
| TP1-5 | Test points | 1mm pad | I2S clk/data, button, BAT+ |

## Netlist

Every connection. Anything not listed here should not exist.

### Power

```
BAT+   J1.1 ── SW2.common
       SW2.out ── U1.B+          (see "battery pads" below)
                ── U3.VIN         (amp runs on raw battery, 3.7-4.2V)
                ── C5.+  C3.1  C4.1
GND    J1.2 ── U1.GND ── U2.GND ── U3.GND
                ── C5.-  C1.2  C2.2  C3.2  C4.2
                ── SW1.2  ── U2.L/R  ── U3.GAIN
3V3    U1.3V3 ── U2.VDD ── C1.1  C2.1
```

`U3.VIN` on **BAT+, not 3V3 and not 5V.** The XIAO's 5V pin is dead on battery,
and 3V3 costs about 2.3dB of output. The MAX98357A takes 2.5–5.5V with good
supply rejection, so raw battery is fine — and `GAIN` to GND more than covers
the difference from 5V.

`U2.L/R` to **GND** selects the left channel, which is what the firmware reads.
Floating gives silence on that channel and looks exactly like a dead mic.

`U3.GAIN` to **GND** = 12dB. For 15dB use 100kΩ to GND instead; leave a footprint
for the resistor so you can decide after hearing it in the case.

### Signals

```
U1.D8  (GPIO7)  ── U2.SCK        I2S mic bit clock
U1.D9  (GPIO8)  ── U2.WS         I2S mic word select
U1.D10 (GPIO9)  ── U2.SD         I2S mic data

U1.D0  (GPIO1)  ── U3.BCLK       I2S amp bit clock
U1.D1  (GPIO2)  ── U3.LRC        I2S amp word select
U1.D2  (GPIO3)  ── U3.DIN        I2S amp data

U1.D3  (GPIO4)  ── SW1.1         button, INPUT_PULLUP, other side to GND
U1.D4  (GPIO5)  ── U3.SD         amp shutdown — the battery-life pin

U3.+ ── J2.1                     speaker
U3.- ── J2.2                     bridged output: neither side to GND
```

Unused and free for later: D5 (GPIO6), D6 (GPIO43), D7 (GPIO44). D6/D7 are the
UART — leave them clear so serial debugging keeps working.

## Decoupling

One 10µF plus one 100nF per module, placed **as close to the module's power pin
as the layout allows**. On a breadboard you get away with none of this; on a
board with a class-D amplifier switching next to a microphone you do not.

**C5, 220µF across the amp supply, is the one people skip.** The MAX98357A
draws current in bursts at the switching frequency, and without bulk
capacitance those bursts show up as supply ripple — which the microphone and
the ESP32's ADC both see. Cheap insurance.

## Layout rules

**Put U2 and U3 at opposite ends of the board.** The microphone hears the
speaker, and physical distance is the only fix — no amount of filtering
recovers a recording with the confirmation mixed into it. Get as much
separation as the outline allows, and keep the speaker leads away from the mic
traces.

**Ground pour on both layers**, stitched with vias, and keep the I2S clock
lines short and roughly equal length. They run at ~1.5MHz, which is slow enough
to be forgiving, but the amp's switching output is not.

**Keep the XIAO's antenna end clear** — no pour, no traces, no battery under
it. The antenna is at the USB end of the module. Copper near it detunes the
radio, and you have already seen how much WiFi reliability matters.

**Button placement is a mechanical decision, not an electrical one.** It has to
land where her thumb rests, roughly a third down the case. Fix that position in
the enclosure model first, then place the footprint to match.

## Battery pads: the awkward bit

The XIAO's `B+` and `B-` are small pads on the **underside** of the module,
which a hand-soldered carrier cannot reach.

Options, least bad first:

**Two short flying leads.** Put J1 and SW2 on the carrier, run 2 short wires up
to the XIAO's underside pads before soldering the module down. Inelegant but
completely reliable, and it is what most XIAO carriers do.

**Cut-out under the module.** Put a slot in the PCB beneath the battery pads so
you can solder them after the module is mounted. Tidier, one more thing to get
wrong on a first board.

Do not try to power the XIAO through its `5V` pin from the battery — that pin
expects 5V and the charger will not see the cell.

## SW2 — battery isolation

A slide switch between the cell and everything else. Not for her to use; it
lives inside the case. It exists so you can work on the board without
unplugging the battery, and so it can be stored genuinely off. Two minutes of
design for a lot of convenience later.

## Mechanical

Board outline is set by the case, not the other way round. Constraints so far:

- Battery 803040 = **8 × 30 × 40mm**, budget ~12 × 35 × 45mm with foam
- Speaker 40mm diameter, firing out the **front face**
- Case target ~160 × 60 × 28mm
- Mic port on the **top edge**, away from where fingers wrap

Realistically that leaves about **50 × 45mm** for the board, sitting above the
battery. Draw the case first, then fit the board to it.

## Before ordering

- [ ] Every net above checked against the schematic, twice
- [ ] Footprints match the parts you actually bought, not similar ones
- [ ] The tactile switch is the one she chose by feel
- [ ] Board outline checked against the case model, with the battery in place
- [ ] Antenna end clear of copper
- [ ] Mic and amp at opposite ends
- [ ] Test points reachable with the board mounted
- [ ] Order **5 boards** — they cost almost nothing, shipping is the expense

Budget two revisions and 2–3 weeks each. Start now even though the firmware is
already done; that lead time runs in parallel with everything else.
