# A2 correction record

A2 supersedes A1. The reviewed copper board has zero DRC violations, zero
unconnected items and zero full schematic-parity findings. ERC is zero.
The electrical specification matches 17 nets, 75 connected terminals and four
intentional no-connects. All 79 logical PCB terminals match that schematic.

| A1 finding | A2 correction |
|---|---|
| Missing solder-mask openings | Restored on all 81 physical plated pads, including duplicate pads; top and bottom mask Gerbers contain real apertures/artwork. Restored non-plated hole mask definitions to match source libraries. |
| 100 mA battery switch | Replaced with C&K 1101M2S3CQE2, rated 6 A at 28 VDC; new 4.70 mm pitch / 1.85 mm hole footprint. |
| Unprotected amplifier SD | Added R6 = 2.2 kΩ series and R7 = 10 kΩ pull-down. |
| Sleep shutdown not retained | Firmware uses RTC output hold, releases it before normal operation, and mutes before clock teardown. |
| Native schematic parity mismatch | Exact net names, footprint IDs, component metadata, no-connect nets and mechanical-only attributes synchronized. |

The board retains the 120 × 45 mm R8 outline and centered mic. New parts are
R6, R7 and the replacement switch. Do not substitute the A1 switch.

Final reports: `artifacts/final-drc.json`, `erc.txt`, `a2-fabrication-audit.json`.
The ZIP is compared byte-for-byte with exports and SHA256 hashes recorded.
`pcb/check_board.py` now requires solder-mask openings and full parity, unlike
the earlier connectivity-only check. `pcb/audit_preorder.py` verifies the mask
exports and the A2 archive. Final native KiCad source is authoritative; the
placement scripts intentionally reset routing and are not routine build steps.

Physical fit of the owned mic/button, XIAO rear solder access, charging current
and termination, and measured sleep current remain unverified. These are not
claimed as fixed by CAD checks. See ASSEMBLY.md for the 1:1 fit drawing and
bring-up procedure. A2 is a prototype design, not hardware-validated production.

## Firmware validation

Full compile and link passed with Arduino CLI 1.5.1, ESP32 core 3.3.11,
WiFiManager 2.0.17, XIAO ESP32S3, OPI PSRAM and USB CDC. Sketch uses
1,181,510 bytes (35%); globals 52,260 bytes (15%). Staged and current source
hashes match. Placeholder credentials were used; no board was flashed.
See `artifacts/firmware-validation.txt`.
