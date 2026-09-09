"""Apply project-local footprints and conservative routing classes."""
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent/'remote'
replacements={'J3':'XIAO_Left','J4':'XIAO_Right','J6':'XIAO_Battery_SolderAccess','U2':'INMP441_Round_ChipUp','U3':'MAX98357A_Adafruit_Input','J5':'MAX98357A_Adafruit_Speaker','SW2':'SW_CK_1101M2S3CQE2'}
sch=ROOT/'remote.kicad_sch'
text=sch.read_text(encoding='utf-8')
# These fields occur once per placed component; embedded library fields have no
# matching full reference. Walk top-level forms rather than replacing libraries.
depth=0;quoted=False;escape=False;start=0;blocks=[]
for i,c in enumerate(text):
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
        if depth==1:blocks.append((start,i+1))
for a,z in reversed(blocks):
    block=text[a:z]
    if not re.match(r'\(symbol\s',block):continue
    ref=re.search(r'\(property "Reference" "([^"]+)"',block)
    if ref and ref[1] in replacements:
        block=re.sub(r'(\(property "Footprint" )"[^"]*"',lambda m:m[1]+'"revgen:'+replacements[ref[1]]+'"',block)
        text=text[:a]+block+text[z:]
sch.write_text(text,encoding='utf-8')
(ROOT/'fp-lib-table').write_text('(fp_lib_table\n  (version 7)\n  (lib (name "revgen")(type "KiCad")(uri "${KIPRJMOD}/revgen.pretty")(options "")(descr "RevGen module-specific interfaces"))\n)\n')
pro=ROOT/'remote.kicad_pro'
d=json.loads(pro.read_text());base=d['net_settings']['classes'][0]
base.update(track_width=.25,clearance=.2,via_diameter=.7,via_drill=.3)
classes=[base]
for name,width,priority in [('Power',1.0,0),('Speaker',.8,1),('Ground',.6,2),('LogicSupply',.5,3)]:
    c=base.copy();c.update(name=name,track_width=width,priority=priority);classes.append(c)
d['net_settings']['classes']=classes
d['net_settings']['netclass_patterns']=[{'netclass':cls,'pattern':net} for cls,nets in [('Power',['VBAT_IN','VBAT_SW']),('Speaker',['SPK+','SPK-']),('Ground',['GND']),('LogicSupply',['+3V3'])] for net in nets]
rules=d['board']['design_settings']['rules']
rules.update(min_clearance=.2,min_track_width=.25,min_via_diameter=.65,min_through_hole_diameter=.3,min_copper_edge_clearance=.4)
pro.write_text(json.dumps(d,indent=2)+'\n')
print('Updated local library, schematic footprint fields and routing classes.')
