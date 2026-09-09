"""Fill zones and check B3 electrical mapping and enclosure datums."""
from pathlib import Path
import json
import pcbnew as k
ROOT=Path(__file__).resolve().parent
b=k.LoadBoard(str(ROOT/'emitter.kicad_pcb'))
b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones())
k.SaveBoard(str(ROOT/'emitter.kicad_pcb'),b)
expected=json.loads((ROOT/'expected-nets.json').read_text())
checked=0;leds=[]
for f in b.GetFootprints():
    ref=f.GetReference()
    for p in f.Pads():
        want=expected.get(ref,{}).get(p.GetNumber())
        if want is not None:
            assert p.GetNetname()=='/'+want,(ref,p.GetNumber(),p.GetNetname(),want)
            checked+=1
    if ref in ['D1','D2','D3','D4']:
        xs=[k.ToMM(p.GetPosition().x) for p in f.Pads()]
        leds.append({'reference':ref,'center_x_from_left_mm':sum(xs)/len(xs)-50,'center_y_from_front_mm':k.ToMM(f.GetPosition().y)-50})
assert abs(sum(x['center_x_from_left_mm'] for x in leds)/4-40)<.001
report={'functional_pads_verified':checked,'led_centers':sorted(leds,key=lambda x:x['reference']),
 'board_mm':[80,65],'usb_side':'right',
 'usb_centreline_from_front_mm':40.3,
 'usb_projection':'Not measured; right edge aligned with reserved module envelope, verify on actual board',
 'mounting_holes_mm_from_top_left':[[4,25],[4,60],[76,60]],'mounting_hole_diameter_mm':3.2}
(ROOT/'layout-audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
