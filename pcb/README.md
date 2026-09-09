# Remote carrier PCB — A3 prototype

> **A3 replaces A2 and rejected A1 files, correcting amplifier component-up mounting.** Mask openings, switch rating, amplifier protection and native schematic parity are corrected. Check owned-part fit before ordering; charging remains untested.

Completed **120 × 45 mm**, rounded R8, two-layer carrier for existing modules.
Fully routed: **0 DRC violations, 0 unconnected items, 0 ERC messages** under
project rules. All 79 logical pad assignments match the schematic.

- [Manufacturing ZIP](remote/RevGen-Remote-A3-Gerbers.zip)
- [KiCad project](remote/remote.kicad_pro), [PCB](remote/remote.kicad_pcb), [schematic](remote/remote.kicad_sch)
- [Assembly instructions](remote/ASSEMBLY.md)
- [A3 amplifier correction](remote/A3_CORRECTIONS.md)
- [Board preview](remote/artifacts/remote-top.png), [1:1 footprint drawing](remote/artifacts/assembly-1to1.svg), [schematic drawing](remote/artifacts/remote.svg)

Core remote operation was verified on breadboard. Charging hardware and charging
firmware remain untested. Compare the owned mic and button with the 1:1 drawing
before ordering; CAD checks do not establish their physical fit.
The separate 24 kHz playback compatibility finding remains open; see
[fresh review](remote/A2_FRESH_REVIEW.md).

The native schematic is authoritative. A2 adds R6 (2.2 kΩ), R7 (10 kΩ), and
a C&K 1101M2S3CQE2 switch. [Correction record](remote/A2_CORRECTIONS.md). Keep `revgen.pretty` and `fp-lib-table`
alongside the project. `.trace_*` files are historical. Generator scripts reset
placement/routing: do not rerun them over the finished PCB. Intermediate reports
are provenance; final reports are `artifacts/final-drc.json` and `artifacts/erc.txt`.

Validate from the repository root with KiCad 10 on PATH:

```powershell
kicad-cli sch export netlist --format kicadxml --output pcb/remote/artifacts/netlist.xml pcb/remote/remote.kicad_sch
python pcb/check_netlist.py pcb/remote/artifacts/netlist.xml
kicad-cli sch erc --output pcb/remote/artifacts/erc.txt pcb/remote/remote.kicad_sch
kicad-cli pcb drc --schematic-parity --format json --output pcb/remote/artifacts/final-drc.json pcb/remote/remote.kicad_pcb
& 'C:/Program Files/KiCad/10.0/bin/python.exe' pcb/check_board.py
```

Run `pcb/audit_preorder.py` with KiCad Python to check masks, full parity and
the A3 ZIP against current exports. Generator scripts are development tools,
not a single-command reproduction of all manual routing/finish corrections.
