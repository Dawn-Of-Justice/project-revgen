"""Finalize A3 labels, remove redundant NC copper and repair a ground thermal."""
from pathlib import Path
import re
import pcbnew as k
root=Path(__file__).resolve().parent/'remote'
b=k.LoadBoard(str(root/'remote.kicad_pcb'))
remove={str(t.m_Uuid.AsString()) for t in b.GetTracks() if t.GetNetname().startswith('unconnected-')}
p=root/'remote.kicad_pcb';s=p.read_text()
s=re.sub(r'\n\t\((?:segment|via)\s.*?\n\t\)',lambda m:'' if any(u in m[0] for u in remove) else m[0],s,flags=re.S)
p.write_text(s)
b=k.LoadBoard(str(p))
for f in b.GetFootprints():
    if f.GetReference()=='C7':
        for pad in f.Pads():
            if pad.GetNetname()=='/GND':pad.SetLocalZoneConnection(k.ZONE_CONNECTION_FULL)
for d in b.GetDrawings():
    if isinstance(d,k.PCB_TEXT) and abs(k.ToMM(d.GetPosition().y)-137.5)<.01:
        labels={114.88:'VIN',117.42:'GND',119.96:'SD',122.5:'GAIN',125.04:'DIN',127.58:'BCLK',130.12:'LRC'}
        d.SetText(labels[round(k.ToMM(d.GetPosition().x),2)])
if not any(isinstance(d,k.PCB_TEXT) and d.GetText()=='AMP CHIP UP' for d in b.GetDrawings()):
    d=k.PCB_TEXT(b);d.SetText('AMP CHIP UP');d.SetPosition(k.VECTOR2I(k.FromMM(122.5),k.FromMM(144.5)));d.SetLayer(k.F_SilkS);d.SetTextSize(k.VECTOR2I(k.FromMM(.9),k.FromMM(.9)));d.SetTextThickness(k.FromMM(.15));b.Add(d)
k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(p),b)
