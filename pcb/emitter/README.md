# Emitter PCB — current B3

- `native-b3/emitter.kicad_pro`: KiCad project.
- `native-b3/emitter.kicad_pcb`: corrected PCB.
- `native-b3/emitter.kicad_sch`: matching schematic.
- `native-b3/emitter-pcb-top.png`: PCB preview.
- `emitter-B3-prototype-gerbers.zip`: current fabrication package.
- `native-b3/fabrication/`: identical unpacked Gerber/drill files.
- `native-b3/ASSEMBLY.md`: parts, orientation and physical checks.
- `native-b3/README.md`: layout and validation details.
- `revgen_emitter.pretty/`: required recovered 30-pin ESP32 footprint.

Keep the footprint directory alongside native-b3; the project's library table
uses a relative path to it. Superseded layouts and routing intermediates have
been removed. The original user-supplied archive outside this folder is untouched.
