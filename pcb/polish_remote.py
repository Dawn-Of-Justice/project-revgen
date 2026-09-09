"""Resolve final DRC findings and label module assembly orientation."""
from pathlib import Path
import json
import pcbnew as k
ROOT=Path(__file__).resolve().parent/'remote'
mm=k.FromMM
def p(x,y):return k.VECTOR2I(mm(x+100),mm(y+50))
d=json.loads((ROOT/'artifacts/final-drc.json').read_text())
dangling={i['uuid'] for v in d['violations'] if v['type']=='track_dangling' for i in v['items']}
boardfile=ROOT/'remote.kicad_pcb'
source=boardfile.read_text(encoding='utf-8');depth=0;quoted=False;escape=False;start=0;remove=[]
for i,c in enumerate(source):
    if quoted:
        if escape:escape=False
        elif c=='\\':escape=True
        elif c=='"':quoted=False
    elif c=='"':quoted=True
    elif c=='(':
        if depth==1:start=i
        depth+=1
    elif c==')':
        depth-=1
        if depth==1 and source[start:start+8]=='(segment' and any(uid in source[start:i+1] for uid in dangling):remove.append((start,i+1))
for a,z in reversed(remove):source=source[:a]+source[z:]
boardfile.write_text(source,encoding='utf-8')
b=k.LoadBoard(str(boardfile))
for fp in b.GetFootprints():
    if fp.GetReference()=='C6':
        for pad in fp.Pads():
            if pad.GetNumber()=='2':pad.SetLocalZoneConnection(k.ZONE_CONNECTION_FULL)
    if fp.GetReference()=='U3':fp.Reference().SetPosition(p(11,91))
for text in b.GetDrawings():
    if isinstance(text,k.PCB_TEXT):
        if text.GetText()=='MIC CHIP UP':text.SetPosition(p(22.5,21.8))
        elif text.GetText()=='HOLD TO TALK':text.SetPosition(p(22.5,55))
        elif text.GetText()=='FITTED 0R':text.SetPosition(p(8,85))
        if text.GetLayer() in (k.F_SilkS,k.B_SilkS):
            size=text.GetTextSize();text.SetTextSize(k.VECTOR2I(max(size.x,mm(.8)),max(size.y,mm(.8))))
def label(s,x,y,size=.7,angle=0,back=False):
    # Idempotent by label+position, without changing unrelated text.
    if any(isinstance(t,k.PCB_TEXT) and t.GetText()==s and t.GetPosition()==p(x,y) for t in b.GetDrawings()):return
    size=max(size,.8)
    t=k.PCB_TEXT(b);t.SetText(s);t.SetPosition(p(x,y));t.SetLayer(k.B_SilkS if back else k.F_SilkS);t.SetMirrored(back);t.SetTextAngle(k.EDA_ANGLE(angle,k.DEGREES_T));t.SetTextSize(k.VECTOR2I(mm(size),mm(size)));t.SetTextThickness(mm(.12));b.Add(t)
for x,s in [(14.88,'LRC'),(17.42,'BCLK'),(19.96,'DIN'),(22.5,'GAIN'),(25.04,'SD'),(27.58,'GND'),(30.12,'VIN')]:label(s,x,87.5,.7,90)
for x,s in [(19.96,'L/R'),(22.5,'WS'),(25.04,'SCK')]:label(s,x,24,.65)
label('+',32.5,65,.85);label('-',32.5,63,.85)
label('B+',29.5,10.618,.75,back=True);label('B-',29.5,8.713,.75,back=True)
b.BuildConnectivity();filler=k.ZONE_FILLER(b);filler.Fill(b.Zones());k.SaveBoard(str(ROOT/'remote.kicad_pcb'),b)
print('Removed',len(dangling),'dangling stubs; completed assembly labels and C6 ground connection.')
