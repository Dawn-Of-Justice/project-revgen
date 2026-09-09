"""Complete A3's remaining bottom-layer BCLK connection with clearance-aware search."""
from pathlib import Path
import heapq
import math
import numpy as np
import pcbnew as k
root=Path(__file__).resolve().parent/'remote'
b=k.LoadBoard(str(root/'remote.kicad_pcb'))
net=b.GetNetInfo().GetNetItem('/I2S_AMP_DIN')
step=.1
xs=np.arange(100,145.0001,step);ys=np.arange(50,170.0001,step)
X,Y=np.meshgrid(xs,ys);blocked=(X<100.7)|(X>144.3)|(Y<50.7)|(Y>169.3)
for cx,cy,cond in [(108,58,(X<108)&(Y<58)),(137,58,(X>137)&(Y<58)),(108,162,(X<108)&(Y>162)),(137,162,(X>137)&(Y>162))]:
    blocked |= cond & ((X-cx)**2+(Y-cy)**2>7.3**2)
margin=.2+.125+.08
for f in b.GetFootprints():
    for p in f.Pads():
        if p.GetNetCode()==net.GetNetCode() or not p.IsOnLayer(k.B_Cu):continue
        bb=p.GetBoundingBox()
        blocked |= (X>=k.ToMM(bb.GetLeft())-margin)&(X<=k.ToMM(bb.GetRight())+margin)&(Y>=k.ToMM(bb.GetTop())-margin)&(Y<=k.ToMM(bb.GetBottom())+margin)
for t in b.GetTracks():
    if t.GetNetCode()==net.GetNetCode() or not t.IsOnLayer(k.B_Cu):continue
    a,c=t.GetStart(),t.GetEnd();ax,ay=k.ToMM(a.x),k.ToMM(a.y);cx,cy=k.ToMM(c.x),k.ToMM(c.y)
    dx,dy=cx-ax,cy-ay;den=dx*dx+dy*dy
    u=np.clip(((X-ax)*dx+(Y-ay)*dy)/den,0,1) if den else 0
    width=t.GetWidth(k.B_Cu) if isinstance(t,k.PCB_VIA) else t.GetWidth()
    blocked |= (X-ax-u*dx)**2+(Y-ay-u*dy)**2 < (k.ToMM(width)/2+margin)**2
# Existing external antenna keepout on both copper layers.
blocked |= (X>=100.5-margin)&(X<=110+margin)&(Y>=104-margin)&(Y<=110+margin)
def index(x,y):return round((y-50)/step),round((x-100)/step)
start=index(123.38,58.46);end=index(104.0,122.0)
assert not blocked[start] and not blocked[end]
queue=[(0,0,start)];cost={start:0};prev={};found=False
directions=[(a,c) for a in [-1,0,1] for c in [-1,0,1] if a or c]
while queue:
    _,g,u=heapq.heappop(queue)
    if g!=cost[u]:continue
    if u==end:found=True;break
    for dy,dx in directions:
        v=(u[0]+dy,u[1]+dx)
        if not (0<=v[0]<blocked.shape[0] and 0<=v[1]<blocked.shape[1]) or blocked[v]:continue
        if dy and dx and (blocked[u[0]+dy,u[1]] or blocked[u[0],u[1]+dx]):continue
        ng=g+math.hypot(dx,dy)
        if ng<cost.get(v,math.inf):
            cost[v]=ng;prev[v]=u
            heapq.heappush(queue,(ng+math.hypot(v[0]-end[0],v[1]-end[1]),ng,v))
assert found,'No bottom-layer path with conservative clearance'
path=[end]
while path[-1]!=start:path.append(prev[path[-1]])
path.reverse();simple=[path[0]]
for i in range(1,len(path)-1):
    if (path[i][0]-path[i-1][0],path[i][1]-path[i-1][1])!=(path[i+1][0]-path[i][0],path[i+1][1]-path[i][1]):simple.append(path[i])
simple.append(path[-1]);points=[(123.38,58.46)]+[(xs[x],ys[y]) for y,x in simple]+[(104.0,122.0)]
for a,c in zip(points,points[1:]):
    t=k.PCB_TRACK(b);t.SetStart(k.VECTOR2I(k.FromMM(float(a[0])),k.FromMM(float(a[1]))));t.SetEnd(k.VECTOR2I(k.FromMM(float(c[0])),k.FromMM(float(c[1]))));t.SetWidth(k.FromMM(.25));t.SetLayer(k.B_Cu);t.SetNetCode(net.GetNetCode());b.Add(t)
b.BuildConnectivity();filler=k.ZONE_FILLER(b);filler.Fill(b.Zones());k.SaveBoard(str(root/'remote.kicad_pcb'),b)
print('Completed bottom-layer data path:',len(points)-1,'segments; run full DRC.')

