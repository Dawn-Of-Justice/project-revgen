# Emitter B3 prototype assembly

Board: 80 x 65 mm rounded rectangle, two copper layers, FR-4, 1.6 mm thickness,
1 oz copper. Standard lead-free HASL is suitable. Three 3.2 mm non-plated
mounting holes. No gold fingers, castellations, or edge plating. Use both PTH
and NPTH drill files with the seven copper/mask/silkscreen/outline Gerbers.

## Parts and fit

| Reference | Part / value | Board footprint requirement |
|---|---|---|
| U1 | Owned classic 30-pin ESP32 development board | 15 pins per row, 2.54 mm pitch, 25.40 mm between rows; 1.0 mm holes |
| D1-D4 | Everlight IR333C/H0/L10, 940 nm | 5 mm radial body, 2.54 mm leads |
| R1-R4 | 100 ohm, 0.25 W each | Axial, 7.62 mm formed lead pitch; 6.3 x 2.5 mm body |
| R5 | 220 ohm | Same axial footprint |
| R6,R7 | 10 kohm | Same axial footprint |
| Q1 | AO3400A | SOT-23, gate 1 / source 2 / drain 3 |
| C1,C2 | 100 nF ceramic, rated at least 10 V | 2.50 mm lead pitch; 5.0 mm diameter, 2.5 mm thick body |
| C3 | 100 uF, at least 10 V | Radial electrolytic, 6.3 mm diameter, 2.50 mm leads |
| J1 | 1x3 header or wired receiver connection | 2.54 mm pitch |
| SW1 | Normally open 6 mm tactile switch | Standard four-leg 6 mm footprint, 6.5 x 4.5 mm pin grid |

U1 spacing comes from the user's original Gerbers, not the rejected 38-pin
ESP32 documentation. The module body/USB envelope is reserved clearance, not
a measured case drawing. Check cable access and body fit at full scale before
ordering an enclosure. Female header sockets can make the ESP32 removable;
check the actual board's pins and socket height before fitting other hardware.

## Orientation and operation

- Component side up: ESP32 antenna toward the `ANTENNA` area,
  USB toward the `USB` label. Square U1 pad 1 is EN at the lower left; USB faces right.
- LED pad 1 is cathode (flat side), pad 2 is anode. The cathodes connect to
  Q1 drain; each anode has its own 100 ohm resistor. Do not substitute the old
  NPN into Q1's MOSFET footprint.
- All four LEDs send the same signal. During assembly, form D2/D3 toward the
  front and D1/D4 toward the left/right as the enclosure permits. Their stock
  footprint/3D model is upright; coverage angles are set by lead forming and
  must be tested. Four narrow-beam LEDs do not guarantee all-around coverage.
- C3 positive goes to the silkscreen `+`. Its stripe/negative goes to GND.
- J1 pins 1/2/3 are 3V3/GND/OUT. Use wires to adapt the receiver's actual pin
  order. It must explicitly support 3.3 V supply and logic. A generic receiver
  part name alone does not establish its pinout or supply rating.
- SW1 joins GPIO27 to ground while pressed. Hold five seconds with the new
  learning firmware; receiver OUT is GPIO15 and transmit drive is GPIO4.

## Checks still requiring hardware

Confirm the owned ESP32's USB-derived VIN rail provides approximately 5 V and
can supply the LED load alongside ESP32 Wi-Fi peaks. At 5 V with an illustrative
1.3 V LED drop, each branch is about 37 mA while on (148 mA for four). The power
path inside the development board cannot be established from carrier Gerbers.

Before connecting USB, check for shorts and component polarity. Then verify
receiver capture, physical replay, learning-button behavior, and the coverage
at the intended installation distance. The learning firmware/backend changes
must be flashed/deployed separately; PCB completion does not perform those steps.

CAD status: strict PCB DRC and schematic parity have zero violations or unconnected pads; schematic ERC has zero errors and warnings. No physical build
of this four-LED revision has yet been tested.

