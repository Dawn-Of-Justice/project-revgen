"""Fabrication checks beyond ERC/DRC. Run using KiCad's Python interpreter."""
from pathlib import Path
import collections
import hashlib
import json
import sys
import zipfile
import pcbnew as k

root = Path(__file__).resolve().parent / 'remote'
board = k.LoadBoard(str(root / 'remote.kicad_pcb'))
missing = []
for footprint in board.GetFootprints():
    for pad in footprint.Pads():
        if pad.GetAttribute() == k.PAD_ATTRIB_PTH:
            if not (pad.IsOnLayer(k.F_Mask) and pad.IsOnLayer(k.B_Mask)):
                missing.append(f'{footprint.GetReference()}.{pad.GetNumber()}')
empty_masks = []
for name in ['remote-F_Mask.gts', 'remote-B_Mask.gbs']:
    source = (root / 'manufacturing' / name).read_text()
    if '%ADD' not in source:
        empty_masks.append(name)
with zipfile.ZipFile(root / 'RevGen-Remote-A3-Gerbers.zip') as archive:
    zip_matches = all(archive.read(p.name) == p.read_bytes()
                      for p in (root / 'manufacturing').iterdir())
parity = json.loads((root / 'artifacts/final-drc.json').read_text())
result = {
    'board_sha256': hashlib.sha256((root / 'remote.kicad_pcb').read_bytes()).hexdigest(),
    'pth_pads_missing_mask_openings': missing,
    'mask_files_without_apertures': empty_masks,
    'fabrication_zip_matches_exports': zip_matches,
    'drc_violations': len(parity['violations']),
    'unconnected_items': len(parity['unconnected_items']),
    'schematic_parity_counts': dict(collections.Counter(
        issue['type'] for issue in parity['schematic_parity'])),
    'scope': 'Automated fabrication audit only; electrical ratings and physical fit require separate review.'
}
(root / 'artifacts/a3-fabrication-audit.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
sys.exit(1 if missing or empty_masks or not zip_matches or parity['violations'] or parity['unconnected_items'] or parity['schematic_parity'] else 0)
