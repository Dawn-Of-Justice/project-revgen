"""Verify component-up carrier coordinates against the original Eagle board."""
from pathlib import Path
import math
import xml.etree.ElementTree as ET
import pcbnew as k
root=Path(__file__).resolve().parent/'remote'
e=ET.parse(root/'sources/adafruit-max98357.brd')
elements={el.get('name'):el for el in e.findall('.//board/elements/element')}
def eagle_pad(element,number):
    el=elements[element]
    assert not el.get('rot','').startswith('M'), 'Unexpected mirrored source element'
    package=e.find(f".//library[@name='{el.get('library')}']/packages/package[@name='{el.get('package')}']")
    pad=package.find(f"pad[@name='{number}']")
    angle=math.radians(float(el.get('rot','R0')[1:]))
    x,y=float(pad.get('x')),float(pad.get('y'))
    return (float(el.get('x'))+x*math.cos(angle)-y*math.sin(angle),float(el.get('y'))+x*math.sin(angle)+y*math.cos(angle))
origin=(float(elements['JP1'].get('x')),float(elements['JP1'].get('y')))
board=k.LoadBoard(str(root/'remote.kicad_pcb'))
fps={f.GetReference():f for f in board.GetFootprints()}
center=fps['U3'].GetPosition()
# Convert Eagle top view to KiCad and rotate 180 degrees: (dx,dy)->(-dx,+dy).
# Carrier logical BCLK/LRC/DIN pins are 5/6/7, Eagle physical positions 6/7/5.
for ref,logical,element,physical in [('U3','1','JP1','1'),('U3','2','JP1','2'),('U3','3','JP1','3'),('U3','4','JP1','4'),('U3','5','JP1','6'),('U3','6','JP1','7'),('U3','7','JP1','5'),('J5','1','X1','2'),('J5','2','X1','1')]:
    x,y=eagle_pad(element,physical)
    expected=(-(x-origin[0]),y-origin[1])
    pad=next(p for p in fps[ref].Pads() if p.GetNumber()==logical)
    actual=(k.ToMM(pad.GetPosition().x-center.x),k.ToMM(pad.GetPosition().y-center.y))
    assert all(abs(a-b)<.00001 for a,b in zip(actual,expected)),(ref,logical,actual,expected)
for track in board.GetTracks():
    if isinstance(track,k.PCB_VIA):continue
    width=k.ToMM(track.GetWidth())
    name=track.GetNetname()
    minimum=1.0 if name in ('/VBAT_SW','/VBAT_IN') else .8 if name in ('/SPK+','/SPK-') else .25
    assert width>=minimum-1e-6,(name,width,minimum)
print('PASS: all 9 amplifier pads match component-up Eagle transform; battery and speaker track widths preserved.')
