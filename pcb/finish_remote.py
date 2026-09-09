"""Import routing, add ground planes, and place readable silkscreen references."""
from pathlib import Path
import math
import pcbnew as k
ROOT=Path(__file__).resolve().parent/'remote'
mm=k.FromMM
def v(x,y):return k.VECTOR2I(mm(x),mm(y))
def p(x,y):return v(x+100,y+50)
def layerset(ls):
    s=k.LSET()
    for layer in ls:s.AddLayer(layer)
    return s
b=k.LoadBoard(str(ROOT/'remote.kicad_pcb'))
assert k.ImportSpecctraSES(b,str(ROOT/'artifacts/routed.ses')),'SES import failed'
ground=b.GetNetInfo().GetNetItem('GND')
for layer in [k.F_Cu,k.B_Cu]:
    z=k.ZONE(b);z.SetLayer(layer);z.SetNetCode(ground.GetNetCode());z.SetLocalClearance(mm(.25));z.SetThermalReliefGap(mm(.3));z.SetThermalReliefSpokeWidth(mm(.3));z.SetPadConnection(k.ZONE_CONNECTION_THERMAL);z.SetMinThickness(mm(.25))
    outline=z.Outline();outline.NewOutline()
    for x,y in [(100.4,50.4),(144.6,50.4),(144.6,169.6),(100.4,169.6)]:outline.Append(mm(x),mm(y))
    b.Add(z)

def distance(x,y,a,c):
    ax,ay=k.ToMM(a.x),k.ToMM(a.y);cx,cy=k.ToMM(c.x),k.ToMM(c.y)
    dx,dy=cx-ax,cy-ay;t=max(0,min(1,((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy))) if dx or dy else 0
    return math.hypot(x-ax-t*dx,y-ay-t*dy)
def clear(x,y):
    pos=v(x,y)
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            box=pad.GetBoundingBox();box.Inflate(mm(.6))
            if box.Contains(pos):return False
    for t in b.GetTracks():
        width=t.GetWidth(k.F_Cu) if isinstance(t,k.PCB_VIA) else t.GetWidth()
        if t.GetNetCode()!=ground.GetNetCode() and distance(x,y,t.GetStart(),t.GetEnd()) < k.ToMM(width)/2+.6:return False
    for z in b.Zones():
        if z.GetIsRuleArea() and z.Outline().Contains(pos):return False
    return True
count=0
for x,y in [(2,yy) for yy in range(14,111,12)]+[(43,yy) for yy in range(14,111,12)]+[(12,62),(30,62),(12,86),(32,111)]:
    if clear(x+100,y+50):
        via=k.PCB_VIA(b);via.SetPosition(p(x,y));via.SetWidth(mm(.7));via.SetDrill(mm(.3));via.SetViaType(k.VIATYPE_THROUGH);via.SetLayerPair(k.F_Cu,k.B_Cu);via.SetNetCode(ground.GetNetCode());b.Add(via);count+=1

# Top reference text is placed outside visible copper and silkscreen graphics.
obstacles=[]
for fp in b.GetFootprints():
    for pad in fp.Pads():
        bb=pad.GetBoundingBox();bb.Inflate(mm(.22));obstacles.append(bb)
    for g in fp.GraphicalItems():
        if g.GetLayer()==k.F_SilkS:
            bb=g.GetBoundingBox();bb.Inflate(mm(.15));obstacles.append(bb)
for g in b.GetDrawings():
    if g.GetLayer()==k.F_SilkS:
        bb=g.GetBoundingBox();bb.Inflate(mm(.15));obstacles.append(bb)
for fp in sorted(b.GetFootprints(),key=lambda f:f.GetReference()):
    ref=fp.Reference()
    if not ref.IsVisible():continue
    anchor=ref.GetPosition();ax,ay=k.ToMM(anchor.x),k.ToMM(anchor.y)
    options=sorted([(dx,dy) for dx in [0,-2,2,-4,4,-6,6,-8,8] for dy in [0,-1.5,1.5,-3,3,-4.5,4.5,-6,6]],key=lambda t:t[0]*t[0]+t[1]*t[1])
    for dx,dy in options:
        ref.SetPosition(v(ax+dx,ay+dy));bb=ref.GetBoundingBox();bb.Inflate(mm(.1))
        if bb.GetLeft()<mm(101) or bb.GetRight()>mm(144) or bb.GetTop()<mm(51) or bb.GetBottom()>mm(169):continue
        if not any(bb.Intersects(o) for o in obstacles):obstacles.append(bb);break
    else:print('Reference requires inspection:',fp.GetReference())
    if fp.GetReference()=='R1':fp.SetAttributes(fp.GetAttributes()|k.FP_DNP)
b.BuildConnectivity();filler=k.ZONE_FILLER(b);filler.Fill(b.Zones());k.SaveBoard(str(ROOT/'remote.kicad_pcb'),b)
print('Imported routing and filled two ground planes;',count,'ground stitching vias.')
