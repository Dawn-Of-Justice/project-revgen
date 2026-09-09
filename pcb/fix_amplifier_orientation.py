"""One-time A2 to A3 conversion: component-up Adafruit module mounting."""
from pathlib import Path
import re
import shutil
import pcbnew as k

root=Path(__file__).resolve().parent/'remote'
backup=root/'artifacts/a2-before-amplifier-fix'
assert not backup.exists(), 'Conversion already started; do not repeat'
backup.mkdir()
for name in ['remote.kicad_pcb','remote.kicad_sch','remote.kicad_pro','ASSEMBLY.md','artifacts/release-manifest.json']:
    shutil.copy2(root/name,backup/Path(name).name)
shutil.copytree(root/'manufacturing',backup/'manufacturing')
shutil.copytree(root/'revgen.pretty',backup/'revgen.pretty')
b=k.LoadBoard(str(root/'remote.kicad_pcb'))
fps={f.GetReference():f for f in b.GetFootprints()}
affected={p.GetNetCode() for ref in ('U3','J5') for p in fps[ref].Pads() if p.GetNetname()!='/GND'}
remove={str(t.m_Uuid.AsString()) for t in b.GetTracks() if t.GetNetCode() in affected}
# Remove complete s-expressions, avoiding SWIG ownership problems with Remove().
source=(root/'remote.kicad_pcb').read_text()
pattern=r'\n\t\((?:segment|via)\s.*?\n\t\)'
source=re.sub(pattern,lambda m:'' if any(u in m[0] for u in remove) else m[0],source,flags=re.S)
(root/'remote.kicad_pcb').write_text(source)
b=k.LoadBoard(str(root/'remote.kicad_pcb'))
for f in b.GetFootprints():
    if f.GetReference() not in ('U3','J5'):continue
    assert f.GetOrientationDegrees()==0
    center=f.GetPosition()
    for p in f.Pads():
        pos=p.GetPosition();p.SetPosition(k.VECTOR2I(2*center.x-pos.x,pos.y))
for name in ('MAX98357A_Adafruit_Input','MAX98357A_Adafruit_Speaker'):
    f=k.FootprintLoad(str(root/'revgen.pretty'),name)
    for p in f.Pads():
        pos=p.GetPosition();p.SetPosition(k.VECTOR2I(-pos.x,pos.y))
    k.PCB_IO_MGR.FindPlugin(k.PCB_IO_MGR.KICAD_SEXP).FootprintSave(str(root/'revgen.pretty'),f)
for drawing in b.GetDrawings():
    if isinstance(drawing,k.PCB_TEXT):
        drawing.SetText(drawing.GetText().replace('REVGEN  A2','REVGEN  A3'))
b.GetTitleBlock().SetRevision('A3')
b.BuildConnectivity()
k.SaveBoard(str(root/'remote.kicad_pcb'),b)
assert k.ExportSpecctraDSN(b,str(root/'artifacts/placement.dsn'))
print('Mirrored U3/J5 pad locations for component-up mounting; removed',len(remove),'affected copper items.')
