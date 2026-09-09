"""Check final copper pad assignments against the exported schematic. Run with KiCad Python."""
from pathlib import Path
import json
import xml.etree.ElementTree as ET
import pcbnew as k

root = Path(__file__).resolve().parent / 'remote'
expected = {}
for net in ET.parse(root / 'artifacts/netlist.xml').findall('./nets/net'):
    name = net.get('name').lstrip('/')
    for node in net.findall('node'):
        if not node.get('ref').startswith('#'):
            expected[node.get('ref'), node.get('pin')] = name
board = k.LoadBoard(str(root / 'remote.kicad_pcb'))
seen = set()
for fp in board.GetFootprints():
    for pad in fp.Pads():
        key = fp.GetReference(), pad.GetNumber()
        if not key[1] or key[0].startswith('H'):
            assert not pad.GetNetCode(), key
            continue
        assert key in expected, ('unexpected pad', key)
        assert pad.GetNetname().lstrip('/') == expected[key], (key, pad.GetNetname(), expected[key])
        seen.add(key)
assert seen == set(expected), ('missing pads', set(expected) - seen)
drc = json.loads((root / 'artifacts/final-drc.json').read_text())
assert not drc['violations'] and not drc['unconnected_items'] and not drc['schematic_parity']
assert all(p.IsOnLayer(k.F_Mask) and p.IsOnLayer(k.B_Mask) for f in board.GetFootprints() for p in f.Pads() if p.GetAttribute()==k.PAD_ATTRIB_PTH)
for path in (root / 'manufacturing').iterdir():
    data = path.read_text()
    assert len(data) > 100, path
    if path.suffix == '.drl':
        assert 'METRIC' in data and 'M30' in data, path
    elif path.suffix != '.gbrjob':
        assert 'M02*' in data, path
print(f'PASS: {len(seen)} logical pads match schematic; DRC 0; unrouted 0; fabrication files valid.')
