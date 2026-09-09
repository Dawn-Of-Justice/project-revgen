# Original emitter Gerber recovery — 2026-09-08

Source: user-supplied `Gerber_revgen_PCB_revgen_2026-09-08.zip`.
Extracted under `pcb/emitter/original-gerbers`; original files are unmodified.
This archive supersedes the schematic PDF for evidence of fabricated routing.

## Geometry recovered

- Two copper layers; 30 ESP32 holes, 15 per row.
- Header pitch: 2.54 mm. Row spacing: **25.40 mm**.
- Header run: 35.56 mm between first and last pin centres.
- Original ESP32 drills: 0.915 mm.
- Original coordinates: x=21.336 through 56.896 mm;
  y=-18.034 and -43.434 mm.
- Outline extents: 78.867 x 62.992 mm. The left edge is slightly slanted:
  x=0 at the top and x=0.254 at the bottom; it is not an exact rectangle.
- Four 3 mm nonplated mounting holes.

Prepared `pcb/emitter/revgen_emitter.pretty/ESP32_30pin_recovered.kicad_mod`
with these header centres (rotated into antenna-up orientation). New pads are
1.8 mm with 1.0 mm drill, intentionally slightly larger than original drills.
Pin numbering is left top-to-bottom 1–15, right bottom-to-top 16–30,
matching the original pinout image. KiCad loads all 30 pads successfully.
This is a header footprint, not a finished carrier or full module courtyard.

## Copper findings

Top-side view has ESP32 USB to the left and antenna to the right, using the
original 30-pin pinout image as the mapping reference. Copper was traced using
Gerber line endpoints and plated-hole layer joins, then compared with the
rendered composite. This is not a complete fabrication DRC or short-circuit audit.

- **Transistor base via R4 routes to GPIO25**, not old firmware GPIO5 or
  current firmware GPIO4. This is a concrete hardware/software mismatch.
  User has not confirmed whether it was the historically repaired pin.
- Positive rail is **3V3**, feeding receiver supply, R1, R2 and R3.
  The previous PDF-derived 5 V pull-up finding does not describe this copper.
- Receiver OUT goes to **GPIO15**, with C1 across OUT/GND and R3 to 3V3.
  Current capture firmware GPIO15 therefore agrees with this PCB.
- R1 pulls **GPIO2** to 3V3, rather than GPIO12 as in the PDF.
  It connects to the button's wired side through a via. Avoid pulling GPIO2
  high externally because it participates in serial download boot selection.
- The connector labelled `IN(D27)` actually routes to **GPIO16**.
  Its VCC and GND labels do agree with 3V3 and ground.
- Transistor left pad routes to the LED pad marked `+`; centre pad to base
  resistor R4; right pad to ground. For P2N2222A C-B-E ordering, collector
  therefore reaches the LED anode marking. The other LED pad goes through R2
  to 3V3. Reverse the LED electrical assignment in the replacement design:
  anode toward supply resistor, cathode toward collector.

Gerbers do not record fitted resistor values, transistor identity, or later
hand-wired modifications. Do not transplant PDF reference/value assignments
blindly: reference names and pin connections differ between these revisions.

## Replacement design decisions

Use this 30-pin, 25.4 mm row-spacing geometry. Route the driver input to GPIO4
to match the firmware already flashed; leave GPIO5/GPIO25 unused for IR.
Keep receiver OUT on GPIO15, move C1 to its supply, and keep logic at 3V3.
Use GPIO27 for an optional button rather than GPIO2/GPIO12; button support
would still require firmware. Omit the misleading speaker connector unless
its accessory is required. Retain the conservative single-LED driver plan
in EMITTER_CIRCUIT_REVIEW.md, with explicit A/K and C/B/E pad assignments.

The old Gerbers are reference material, **not corrected manufacturing files**.
Native schematic reconstruction, routing and ERC/DRC/parity remain pending.
