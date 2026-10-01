# Emitter B3 — centered LEDs and side USB

Latest enclosure-oriented layout, 2026-09-09. Supersedes B2's placement while
preserving its electrical circuit. Created and routed through KiCad MCP with
Freerouting and local KiCad geometry/net verification helpers.

- Board remains 80 x 65 mm, 1.6 mm thick, two layers, 1 oz copper.
- Four LED body centers are at x=25,35,45,55 mm from the left edge and y=5 mm
  from the front edge. Their group is exactly centered on the board.
- ESP32 is rotated 90 degrees: USB toward the right side, antenna toward the
  copper-free left area. Its reserved module envelope meets the right edge.
  Header spacing remains 25.40 mm with 2.54 mm pin pitch. Pad 1 is lower left.
- The right-side USB centreline is nominally 40.3 mm from the front edge,
  assuming the connector is centered between header rows. Actual connector
  offset, projection, height, shell size and cable clearance are NOT measured.
  Measure these on the owned board before finalizing the printed case opening.
- Mounting holes: 3.2 mm, at (4,25), (4,60), (76,60) mm from the top-left corner.
- J1 is the learning receiver header: 1=3V3, 2=GND, 3=IR OUT to GPIO15.
  It is not a power input. Wire the receiver according to its actual pinout;
  select a part explicitly supporting 3.3 V operation. Provide an IR-transparent
  window or opening in the case for reception and transmission.
- SW1 remains the GPIO27 learning button. Provide access through the lid.

Final checks after audit fixes (2026-09-09): KiCad PCB DRC with all-track errors,
schematic parity, all severities and zone refill reports zero violations, zero
unconnected pads and zero schematic parity issues (`strict-drc.txt`). Schematic
ERC also reports zero errors and zero warnings. The custom library was upgraded
with KiCad's native symbol upgrader and its schematic cache refreshed; warnings
were fixed rather than excluded. Placement has no courtyard overlaps or boundary
violations. All 45 functional pads match the expected net map.

C2 is now at (110.5,73.3) mm, beside Q1 at (111,70), with a short local ground
connection and rerouted supply. PCB net names now exactly match schematic names,
including the leading slash. Description and Datasheet fields are synchronized.
The Gerber ZIP and preview were regenerated after these fixes.

Open `emitter.kicad_pcb`; `emitter-pcb-top.png` is the preview. `fabrication/`
holds B3 Gerbers and drill files. Use `../emitter-B3-prototype-gerbers.zip`
for this placement.

Component values, footprint dimensions and electrical precautions are unchanged;
see `ASSEMBLY.md`, with the orientations and mounting coordinates
above taking precedence. LED 3D models are generic upright placeholders. Form
outer LED leads outward and inner LEDs forward as the case requires; centered
placement alone does not establish IR coverage. USB power capacity, receiver
capture and physical replay remain untested on this revision. These physical
checks cannot be cleared through CAD: actual USB dimensions, VIN voltage under
USB power and receiver model/pinout are still needed from the owned hardware.
