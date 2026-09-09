"""Restore manufacturing layers and exact schematic metadata after routing."""
from pathlib import Path
import xml.etree.ElementTree as ET
import pcbnew as k

root = Path(__file__).resolve().parent / 'remote'
b = k.LoadBoard(str(root / 'remote.kicad_pcb'))
xml = ET.parse(root / 'artifacts/netlist.xml')
components = {c.get('ref'): c for c in xml.findall('./components/comp')}
mapping = {}
for net in xml.findall('./nets/net'):
    name = net.get('name')
    if name not in b.GetNetInfo().NetsByName():
        b.Add(k.NETINFO_ITEM(b, name))
    for node in net.findall('node'):
        mapping[node.get('ref'), node.get('pin')] = name
for f in b.GetFootprints():
    ref = f.GetReference()
    if ref.startswith('H'):
        f.SetAttributes(f.GetAttributes() | k.FP_BOARD_ONLY)
        continue
    c = components[ref]
    if ref.startswith('TP'):
        f.SetAttributes(f.GetAttributes() & ~k.FP_EXCLUDE_FROM_BOM)
    lib, name = c.findtext('footprint').split(':', 1)
    f.SetFPID(k.LIB_ID(lib, name))
    f.GetField(k.FIELD_T_DESCRIPTION).SetText(c.findtext('description') or '')
    source_fp=k.FootprintLoad(str(root/'revgen.pretty') if lib=='revgen' else 'C:/Program Files/KiCad/10.0/share/kicad/footprints/'+lib+'.pretty',name)
    source_holes=[p for p in source_fp.Pads() if p.GetAttribute()==k.PAD_ATTRIB_NPTH]
    for pad in f.Pads():
        if pad.GetAttribute()==k.PAD_ATTRIB_NPTH and source_holes:
            pad.SetLayerSet(source_holes[0].GetLayerSet())
        if pad.GetAttribute() == k.PAD_ATTRIB_PTH:
            layers = pad.GetLayerSet()
            layers.AddLayer(k.F_Mask)
            layers.AddLayer(k.B_Mask)
            pad.SetLayerSet(layers)
        key = ref, pad.GetNumber()
        if key in mapping:
            pad.SetNetCode(b.GetNetInfo().GetNetItem(mapping[key]).GetNetCode())
    if ref in ('C1','C6'):
        for pad in f.Pads():
            if pad.GetNumber() == '2':
                pad.SetLocalZoneConnection(k.ZONE_CONNECTION_FULL)
for zone in b.Zones():
    if not zone.GetIsRuleArea():
        zone.SetNetCode(b.GetNetInfo().GetNetItem('/GND').GetNetCode())
b.BuildConnectivity()
# Routing net names also need the schematic's exact leading slash.
for track in b.GetTracks():
    name = track.GetNetname()
    if name and not name.startswith('/') and '/' + name in b.GetNetInfo().NetsByName():
        track.SetNetCode(b.GetNetInfo().GetNetItem('/' + name).GetNetCode())
filler = k.ZONE_FILLER(b)
filler.Fill(b.Zones())
k.SaveBoard(str(root / 'remote.kicad_pcb'), b)
# Confirm the serialized board, not only the in-memory representation.
check = k.LoadBoard(str(root / 'remote.kicad_pcb'))
assert all(p.IsOnLayer(k.F_Mask) and p.IsOnLayer(k.B_Mask)
           for f in check.GetFootprints() for p in f.Pads()
           if p.GetAttribute() == k.PAD_ATTRIB_PTH)
print('Saved and reloaded: PTH mask openings restored; exact schematic names assigned.')
