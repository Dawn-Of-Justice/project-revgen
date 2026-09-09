"""Build RevGen carrier placement from the checked schematic netlist.

Run with KiCad's bundled Python. Routing is performed separately on placement.dsn.
"""
from pathlib import Path
import json
import math
import xml.etree.ElementTree as ET
import pcbnew as k

ROOT = Path(__file__).resolve().parent / 'remote'
LIB = ROOT / 'revgen.pretty'
BOARD = ROOT / 'remote.kicad_pcb'
mm = k.FromMM
def vec(x,y): return k.VECTOR2I(mm(x),mm(y))
def pt(x,y): return vec(x+100,y+50)
def layerset(layers):
    s=k.LSET()
    for layer in layers:s.AddLayer(layer)
    return s

def line(parent,a,b,layer,width=0.15):
    g=k.PCB_SHAPE(parent);g.SetShape(k.SHAPE_T_SEGMENT);g.SetStart(vec(*a));g.SetEnd(vec(*b));g.SetLayer(layer);g.SetWidth(mm(width));parent.Add(g)
    return g

def rect(parent,x1,y1,x2,y2,layer,width=0.15):
    for a,b in [((x1,y1),(x2,y1)),((x2,y1),(x2,y2)),((x2,y2),(x1,y2)),((x1,y2),(x1,y1))]: line(parent,a,b,layer,width)

def pad(fp,n,x,y,kind='tht',size=(1.9,1.9),drill=1):
    p=k.PAD(fp);p.SetNumber(str(n));p.SetPosition(vec(x,y));p.SetSize(vec(*size))
    if kind=='smd':
        p.SetAttribute(k.PAD_ATTRIB_SMD);p.SetShape(k.PAD_SHAPE_ROUNDRECT);p.SetRoundRectRadiusRatio(0.15)
        p.SetLayerSet(layerset([k.F_Cu,k.F_Mask]))
    else:
        p.SetAttribute(k.PAD_ATTRIB_PTH);p.SetShape(k.PAD_SHAPE_RECT if n==1 else k.PAD_SHAPE_OVAL if size[0]!=size[1] else k.PAD_SHAPE_CIRCLE)
        p.SetDrillSize(vec(drill,drill));s=k.LSET.AllCuMask();s.AddLayer(k.F_Mask);s.AddLayer(k.B_Mask);p.SetLayerSet(s)
    fp.Add(p)
    return p

def footprint(name):
    fp=k.FOOTPRINT(None);fp.SetFPID(k.LIB_ID('revgen',name));fp.SetReference('REF**');fp.SetValue(name);fp.SetAttributes(k.FP_THROUGH_HOLE)
    return fp

def savefp(fp):
    k.PCB_IO_MGR.FindPlugin(k.PCB_IO_MGR.KICAD_SEXP).FootprintSave(str(LIB),fp)
    path=LIB/(str(fp.GetFPID().GetLibItemName())+".kicad_mod")
    path.write_text(path.read_text().replace('(layers "*.Cu")','(layers "*.Cu" "*.Mask")'))

def make_libraries():
    # Seeed's XIAO-ESP32-S3-DIP geometry, rotated so USB points toward board top.
    # Split rows retain the schematic J3/J4 identities. SMD lands have no paste.
    for ref,left in [('XIAO_Left',True),('XIAO_Right',False)]:
        fp=footprint(ref)
        for i in range(7):
            y=-7.62+2.54*i if left else 7.62-2.54*i
            pad(fp,i+1,-7.62 if left else 7.62,y,size=(1.524,1.524),drill=1)
            pad(fp,i+1,-8.455 if left else 8.455,y,'smd',(2.432,1.524))
        x1,x2=(-9.95,-6.55) if left else (6.55,9.95)
        rect(fp,x1,-8.9,x2,8.9,k.F_CrtYd,0.05)
        rect(fp,x1,-8.7,x2,8.7,k.F_Fab,0.1)
        savefp(fp)
    # Robu SKU975775, microphone chip faces up, as on the supplied pin-header module.
    # Two 3-pin rows: 2.54mm pitch, nominal 7.62mm separation.
    fp=footprint('INMP441_Round_ChipUp')
    for n,x,y in [(6,2.54,-3.81),(5,0,-3.81),(4,-2.54,-3.81),(3,2.54,3.81),(1,0,3.81),(2,-2.54,3.81)]: pad(fp,n,x,y)
    # Acoustic opening beneath the microphone's bottom port. Integral NPTH pad
    # belongs to the module footprint, not a separate overlapping mount footprint.
    hole=k.PAD(fp);hole.SetNumber('');hole.SetAttribute(k.PAD_ATTRIB_NPTH);hole.SetShape(k.PAD_SHAPE_CIRCLE);hole.SetPosition(vec(0,0));hole.SetSize(vec(3.2,3.2));hole.SetDrillSize(vec(3.2,3.2));hole.SetLayerSet(layerset([k.F_Cu,k.B_Cu,k.F_Mask,k.B_Mask]));fp.Add(hole)
    c=k.PCB_SHAPE(fp);c.SetShape(k.SHAPE_T_CIRCLE);c.SetCenter(vec(0,0));c.SetEnd(vec(7.5,0));c.SetLayer(k.F_CrtYd);c.SetWidth(mm(.05));fp.Add(c)
    c=k.PCB_SHAPE(fp);c.SetShape(k.SHAPE_T_CIRCLE);c.SetCenter(vec(0,0));c.SetEnd(vec(7,0));c.SetLayer(k.F_Fab);c.SetWidth(mm(.1));fp.Add(c)
    savefp(fp)
    # Adafruit product 3006 original Eagle source; input row to speaker row = 12.954mm.
    fp=footprint('MAX98357A_Adafruit_Input')
    # Logical pins 5/6/7 remain BCLK/LRC/DIN, regardless of their physical order.
    # Component side UP, speaker row below: rotate the Eagle top view 180 degrees
    # after converting its upward Y axis to KiCad's downward Y axis.
    for n,x in [(1,-7.62),(2,-5.08),(3,-2.54),(4,0),(7,2.54),(5,5.08),(6,7.62)]: pad(fp,n,x,0)
    rect(fp,-9,-1.5,9,1.5,k.F_CrtYd,.05)
    rect(fp,-8.89,-2.54,8.89,16.51,k.F_Fab,.1)
    savefp(fp)
    fp=footprint('MAX98357A_Adafruit_Speaker')
    # Component-up view: Eagle X1 pad2=VO+ on left, pad1=VO- on right.
    pad(fp,1,-1.7,0,size=(2.2,2.2),drill=1.1);pad(fp,2,1.8,0,size=(2.2,2.2),drill=1.1)
    rect(fp,-3,-1.3,3.1,1.3,k.F_CrtYd,.05);savefp(fp)
    # Seeed SMD land 23=VBAT, 24=GND. Back-access plated holes allow soldering
    # the underside battery pads after aligning the main module rows.
    fp=footprint('XIAO_Battery_SolderAccess')
    pad(fp,1,-4.445,-.382,size=(2.5,1.3),drill=.8)
    pad(fp,2,-4.445,-2.287,size=(2.5,1.3),drill=.8)
    rect(fp,-5.945,-3.187,-2.945,.518,k.F_CrtYd,.05);savefp(fp)

    fp=footprint('SW_CK_1101M2S3CQE2')
    for n,x in [(1,-4.7),(2,0),(3,4.7)]: pad(fp,n,x,0,size=(3,3),drill=1.85)
    rect(fp,-6.35,-3.3,6.35,3.3,k.F_Fab,.1)
    rect(fp,-6.6,-3.55,6.6,3.55,k.F_CrtYd,.05)
    rect(fp,-6.5,-3.45,6.5,3.45,k.F_SilkS,.12)
    savefp(fp)

def make():
    make_libraries()
    b=k.BOARD();b.SetCopperLayerCount(2);fps={}
    xml=ET.parse(ROOT/'artifacts/netlist.xml')
    for comp in xml.findall('./components/comp'):
        ref=comp.get('ref');fpname=comp.findtext('footprint')
        if not fpname:continue
        lib,name=fpname.split(':',1)
        f=k.FootprintLoad(str(LIB) if lib=='revgen' else 'C:/Program Files/KiCad/10.0/share/kicad/footprints/'+lib+'.pretty',name)
        f.SetFPID(k.LIB_ID(lib,name));f.SetReference(ref);f.SetValue(comp.findtext('value'))
        path=k.KIID_PATH();path.push_back(k.KIID('5fcdae05-fabe-4ced-a7c6-6b4d93ca1dcd'));path.push_back(k.KIID(comp.findtext('tstamps')));f.SetPath(path)
        f.SetSheetfile('remote.kicad_sch');f.SetSheetname('remote')
        f.GetField(k.FIELD_T_DESCRIPTION).SetText(comp.findtext('description') or '')
        if ref=='R1':f.SetAttributes(f.GetAttributes()|k.FP_DNP)
        b.Add(f);fps[ref]=f
    # Never infer electrical nets from the earlier PCB: use KiCad's XML export.
    xml=ET.parse(ROOT/'artifacts/netlist.xml')
    mapping={}
    for net in xml.findall('./nets/net'):
        name=net.get('name').lstrip('/')
        if name.startswith('unconnected-'):continue
        if name not in b.GetNetInfo().NetsByName():b.Add(k.NETINFO_ITEM(b,name))
        for node in net.findall('node'):mapping[(node.get('ref'),node.get('pin'))]=name
    for ref,f in fps.items():
        for p in f.Pads():p.SetNetCode(b.GetNetInfo().GetNetItem(mapping[(ref,p.GetNumber())]).GetNetCode() if (ref,p.GetNumber()) in mapping else 0)
    # Board-local mm; XIAO centre 31,11. Its USB end meets the top edge.
    placement={
        'J3':(31,11,0),'J4':(31,11,0),'U2':(22.5,31,0),
        'C1':(5,23,0),'C2':(5,29,0),
        'J6':(31,11,0),'R2':(4,9,0),'R3':(14.16,13.5,180),'C6':(5,18,0),
        'SW1':(16.25,44,0),'R4':(7,43,90),'C7':(7,50,0),
        'U3':(22.5,91,0),'J5':(22.5,103.954,0),
        'C3':(35,90,0),'C4':(35,96,0),'C5':(35,104,0),
        'R5':(17.5,83,0),'R1':(17.5,78,0),'R6':(17.5,65,0),'R7':(17.5,70,0),
        'J2':(21.5,113,0),'J1':(36,65,90),'SW2':(34,75,90),
        'TP1':(4,64,0),'TP2':(4,68,0),'TP3':(4,72,0),
        'TP4':(4,32,0),'TP5':(4,36,0),'TP6':(4,40,0),
        'TP7':(37,49,0),'TP8':(40,81,0),'TP9':(18,18,0),
        'TP10':(37,38,0),'TP11':(4,108,0),
    }
    for ref,(x,y,rot) in placement.items():
        f=fps[ref];f.SetOrientationDegrees(rot);f.SetPosition(pt(x,y))
        f.Reference().SetVisible(True);f.Value().SetVisible(False)
        f.Reference().SetTextSize(vec(.85,.85));f.Reference().SetTextThickness(mm(.13));f.Reference().SetTextAngle(k.EDA_ANGLE(0,k.DEGREES_T))
        f.Reference().SetPosition(pt(x,y-2.8))
        if ref.startswith('TP'):f.Reference().SetPosition(pt(x+2.8,y))
        f.SetLocked(True)
    # Remote silhouette: radius 8mm corners, 120 x 45mm, M2.5 screw clearances.
    for a,z in [((8,0),(37,0)),((45,8),(45,112)),((37,120),(8,120)),((0,112),(0,8))]:line(b,(a[0]+100,a[1]+50),(z[0]+100,z[1]+50),k.Edge_Cuts,.05)
    for a,m,z in [((37,0),(42.656854,2.343146),(45,8)),((45,112),(42.656854,117.656854),(37,120)),((8,120),(2.343146,117.656854),(0,112)),((0,8),(2.343146,2.343146),(8,0))]:
        g=k.PCB_SHAPE(b);g.SetShape(k.SHAPE_T_ARC);g.SetArcGeometry(pt(*a),pt(*m),pt(*z));g.SetLayer(k.Edge_Cuts);g.SetWidth(mm(.05));b.Add(g)
    for i,(x,y) in enumerate([(5,4.5),(41.5,34),(5,115),(40,115)],1):
        f=k.FootprintLoad('C:/Program Files/KiCad/10.0/share/kicad/footprints/MountingHole.pretty','MountingHole_2.7mm_M2.5');f.SetReference('H'+str(i));f.SetPosition(pt(x,y));f.SetAttributes(k.FP_EXCLUDE_FROM_BOM|k.FP_EXCLUDE_FROM_POS_FILES|k.FP_BOARD_ONLY);f.Reference().SetVisible(False);f.Value().SetVisible(False);b.Add(f)
    # Mechanical outlines and keepouts protect modules mounted above the carrier.
    rect(b,122.25,50.5,139.75,71.5,k.Dwgs_User,.15)
    rect(b,113.61,138.46,131.39,157.51,k.Dwgs_User,.15)
    def keepout(x1,y1,x2,y2,layers,tracks=True):
        z=k.ZONE(b);z.SetIsRuleArea(True);z.SetLayerSet(layerset(layers));z.SetDoNotAllowTracks(tracks);z.SetDoNotAllowVias(True);z.SetDoNotAllowZoneFills(True);z.SetDoNotAllowPads(False);z.SetDoNotAllowFootprints(False)
        p=z.Outline();p.NewOutline()
        for x,y in [(x1,y1),(x2,y1),(x2,y2),(x1,y2)]:p.Append(mm(x+100),mm(y+50))
        b.Add(z)
    # No exposed top copper or vias underneath module undersides; bottom traces allowed.
    keepout(24.8,1,37.2,21.5,[k.F_Cu])
    keepout(16,25,29,37,[k.F_Cu])
    keepout(14,93,31,102.4,[k.F_Cu])
    # Reserve a copper-free edge region for external antenna placement/lead exit.
    keepout(.5,54,10,60,[k.F_Cu,k.B_Cu])
    def text(s,x,y,size=1,layer=k.F_SilkS):
        t=k.PCB_TEXT(b);t.SetText(s);t.SetPosition(pt(x,y));t.SetLayer(layer);t.SetTextSize(vec(size,size));t.SetTextThickness(mm(.15));b.Add(t)
    text('REVGEN  A3',23,58,1.4);text('HOLD TO TALK',22.5,53,1)
    text('MIC CHIP UP',22.5,21.8,0.8);text('USB',31,1,0.8,k.Dwgs_User)
    text('AMP CHIP UP',22.5,94.5,.9)
    text('BATTERY',37,60,.85)
    text('FITTED 0R',23,86,.8);text('DNP 100k',23,75,.8)
    text('SPK +  -',22.5,109,.9);text('ANTENNA',6,57,.8,k.Dwgs_User)
    text('3.7V LiPo / prototype',22.5,118,.8)
    # Basic manufacturing limits; actual routing widths also embedded in DSN.
    ds=b.GetDesignSettings();ds.m_MinClearance=mm(.2);ds.m_TrackMinWidth=mm(.25);ds.m_ViasMinSize=mm(.65);ds.m_MinThroughDrill=mm(.3);ds.m_CopperEdgeClearance=mm(.4)
    b.BuildConnectivity();k.SaveBoard(str(BOARD),b)
    k.ExportSpecctraDSN(b,str(ROOT/'artifacts/placement.dsn'))
    (ROOT/'artifacts/placement.json').write_text(json.dumps(placement,indent=2))
    print('Placed',len(list(b.GetFootprints())),'footprints; exported placement.dsn')

if __name__=='__main__':make()
