# Handheld carrier PCB

> **A3 corrects amplifier mounting for component-side-up assembly.** See [correction record](../pcb/remote/A3_CORRECTIONS.md); owned-part fit and charging tests remain pending.

A3 is a routed **120 × 45 mm remote-shaped board with R8 corners**, carrying
existing XIAO ESP32S3, INMP441 and Adafruit MAX98357A modules. The talk button is
central, microphone at top, amplifier/speaker connection at bottom.

See [deliverables and validation](../pcb/README.md) and the
[assembly guide](../pcb/remote/ASSEMBLY.md) for exact footprints, fabrication
files and physical-fit assumptions. The native schematic is organized on A3
with visible local wiring and named connections between sections.

Core operation was verified on breadboard. Charging components and charging
firmware remain untested; first charging tests are planned on this prototype.

## Connections

[netlist.json](netlist.json) is the complete machine-checked electrical spec:
17 nets, 75 connected terminals, four intentional no-connects. All 79 logical
PCB pad assignments match the schematic, including unused pins. Duplicate
physical pads on XIAO lands and the button have also been checked.

| Function | XIAO / GPIO | Destination |
|---|---|---|
| Mic clock | D8 / GPIO7 | SCK |
| Mic word select | D9 / GPIO8 | WS |
| Mic data | D10 / GPIO9 | SD |
| Amp clock | D0 / GPIO1 | BCLK |
| Amp word select | D1 / GPIO2 | LRC |
| Amp data | D2 / GPIO3 | DIN |
| Talk button | D3 / GPIO4 | Switch to ground |
| Amp shutdown/channel | D4 / GPIO5 | 2.2 kΩ series to Amp SD, 10 kΩ pull-down |
| Battery sense | D5 / GPIO6 | 1 MΩ / 1 MΩ divider with 100 nF filter |

J1 positive reaches VBAT_SW through SW2. This feeds XIAO underside B+,
amplifier VIN and the divider. Ground reaches B−. XIAO 3V3 powers the mic;
5V is unused. Mic L/R is grounded. R5 grounds amplifier GAIN; R1 is unpopulated.
Speaker outputs run from integrated module lands J5 to connector J2.
The switched divider consumes no battery current with SW2 off. C6 filters
its high-impedance ADC input. Test pads expose signals, power and ground.

## Layout and verification

Two layers, filled ground planes, 0.2 mm clearance, 0.25 mm signal tracks,
0.5 mm 3V3, 0.8 mm speaker and 1 mm battery supply tracks. Ground stitching
connects the planes. Keepouts provide module underside clearance and an
external antenna area. The mic has an acoustic opening; XIAO uses an external
IPEX antenna requiring suitable enclosure placement.

Final DRC: zero violations and zero unconnected items. ERC: zero messages
under project rules. Reports are `pcb/remote/artifacts/final-drc.json` and
`erc.txt`. These checks do not establish charging functionality or physical
fit. The manufacturing ZIP includes copper, masks, silkscreens, outline and
separate plated/non-plated drills. Keep the local footprint library with
KiCad source. Generator scripts reset layout; do not rerun over the final PCB.

A2 uses C&K 1101M2S3CQE2 (6 A at 28 VDC) for SW2. All plated pads have
solder-mask openings on both faces. Native schematic parity now passes.
