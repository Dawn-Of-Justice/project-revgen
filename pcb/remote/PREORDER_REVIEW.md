# A1 pre-order review — historical rejection

**Resolution:** A2 corrects the design defects below. See [A2_CORRECTIONS.md](A2_CORRECTIONS.md). This report remains evidence for rejecting A1.

Reviewed 2026-09-07 by the main agent and an independent agent given limited
context. This review supersedes earlier statements that A1 was ready to order.
No electrical layout or firmware changes were made during this audit.

## Findings requiring correction before fabrication

1. **P1: Missing solder-mask openings.** All 79 plated through-hole physical
   pads across 33 electrical footprints omit F.Mask and B.Mask. This includes
   module connections, passives, connectors and switch mounting tabs. The
   exported `manufacturing/remote-B_Mask.gbs` contains no apertures or artwork.
   Restore explicit openings in board and library/generator sources, export
   again and inspect the actual Gerbers. The copper continuity check does not
   test solderability. Evidence: `artifacts/preorder-fabrication-audit.json`.
2. **P1: SW2 cannot be approved at the selected rating.** OS102011MS2Q-family
   contacts are rated 0.1 A at 12 VDC. Here the switch carries the combined
   XIAO and amplifier battery current, which can exceed that rating. Select
   a suitably rated switch and matching footprint, or a rated power stage
   controlled by the switch. Do not assume a lower battery voltage permits
   proportionally higher contact current. [Manufacturer datasheet, page 3](https://www.littelfuse.com/assetdocs/littelfuse-ck-slide-os-series-datasheet?assetguid=f8954ac2-65ba-431f-af55-b0493370575e).
3. **P1: Direct AMP_SD drive lacks low-supply protection.** GPIO5 drives
   amplifier SD directly; the Adafruit module has no series resistor here.
   The manufacturer calls for approximately 2 kilohms in series when the
   amplifier supply can fall below 3 V while control logic is 3.3 V. USB with
   the battery disconnected or SW2 off is a relevant state: the XIAO remains
   powered while the amplifier loads the limited charger BAT output. Cold
   boot attempts a beep. Add protection and validate rail behavior; actual
   voltage collapse has not been measured. [MAX98357A datasheet, page 17](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX98357A-MAX98357B.pdf).

## Firmware and assembly issues

- **P2: Amplifier shutdown is not explicitly retained during deep sleep.**
  `ampStop()` drives GPIO5 low using normal GPIO, but `sleepNow()` establishes
  no output hold. The breakout pull-up can release shutdown. With clocks
  absent, typical amplifier standby is about 340 microamps, versus roughly
  0.6 microamps in shutdown. Add retained shutdown or appropriate hardware
  bias, and measure sleep current. This is a firmware correction as well as
  a battery-life verification item, not a proven PCB routing failure.
  [Espressif GPIO hold documentation](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/gpio.html).
- **Mic and button physical fit remains unverified.** Mic 2.54 mm pin pitch
  and 7.62 mm row spacing were inferred. Compare the owned mic and button
  with the 1:1 drawing before committing to these footprints.
- **XIAO rear battery solder access is unproven.** Raised headers need two
  short battery leads. CAD alone does not verify flush mounting clearance
  or reliable rear-access solder joints.
- **Charging works autonomously in the XIAO charger**, but has not been
  tested in this assembly. No charging firmware is required merely to start
  charging. Amplifier load is on the charger BAT rail, so charging speed and
  termination during playback must be checked. Identify the owned XIAO
  revision before assigning an exact charge-current value; current Seeed
  documentation and schematic list differing values.

## What passed, and what those checks mean

Fresh ERC: zero findings under project rules. Copper DRC: zero violations
and zero unrouted connections. Fresh schematic export matches the electrical
spec (16 nets, 71 connections, four no-connects). PCB logical assignments
match all 75 schematic terminals. Firmware GPIO assignments agree with the
circuit. Adafruit input order, speaker-pair spacing and polarity match the
copied official board. XIAO battery polarity agrees with Seeed documentation.
The fabrication ZIP matches the current exports byte for byte.

Full KiCad schematic parity nevertheless reports 173 items: 91 net-name
conflicts, 45 footprint/symbol mismatches, 33 field mismatches, four extra
mounting footprints. Inspected examples include removed leading slashes on
net names and missing footprint library nicknames. Canonical connectivity
matching does not excuse these: normalize metadata and intentional mounting
exclusions so native updates/checks are dependable, then rerun full parity.

Run `pcb/audit_preorder.py` using KiCad Python for mask, archive and full-parity
checks. It currently exits nonzero as expected. Prior `check_board.py` checked
connectivity and file terminators, not manufacturing readiness; its pass is
not sufficient for ordering.

**Decision: do not order the existing A1 Gerber ZIP.** Correct the three P1
items, settle physical-fit assumptions, and regenerate/review fabrication
files before releasing a replacement. Charging and sleep-current measurements
remain prototype bring-up work after those design corrections.
