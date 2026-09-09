"""A3 routing helpers, used with KiCad Python."""
from pathlib import Path
import re
import sys
import pcbnew as k
root=Path(__file__).resolve().parent/'remote'
if sys.argv[1]=='prepare':
    b=k.LoadBoard(str(root/'remote.kicad_pcb'))
    affected={p.GetNetCode() for f in b.GetFootprints() if f.GetReference() in ('U3','J5') for p in f.Pads()}
    remove={str(t.m_Uuid.AsString()) for t in b.GetTracks() if t.GetNetCode() in affected and (t.GetNetname()!='/GND' or not isinstance(t,k.PCB_VIA))}
    source=(root/'remote.kicad_pcb').read_text()
    source=re.sub(r'\n\t\((?:segment|via)\s.*?\n\t\)',lambda m:'' if any(u in m[0] for u in remove) else m[0],source,flags=re.S)
    (root/'remote.kicad_pcb').write_text(source)
    b=k.LoadBoard(str(root/'remote.kicad_pcb'))
    k.ExportSpecctraDSN(b,str(root/'artifacts/placement.dsn'))
    path=root/'artifacts/placement.dsn'
    s=path.read_text().replace('600:300','700:300').replace('(circle F.Cu 600)','(circle F.Cu 700)').replace('(circle B.Cu 600)','(circle B.Cu 700)')
    s=s.replace('(width 200)','(width 250)').replace('(clearance 50 (type smd_smd))','(clearance 200 (type smd_smd))')
    groups=[('Signal',250,'/AMP_GAIN /AMP_SD /AMP_SD_SAFE /BUTTON /I2S_AMP_BCLK /I2S_AMP_DIN /I2S_AMP_LRC /I2S_MIC_SCK /I2S_MIC_SD /I2S_MIC_WS /VBAT_SENSE'),('Power',1000,'/VBAT_IN /VBAT_SW'),('Speaker',800,'/SPK+ "/SPK-"'),('Ground',600,'/GND'),('LogicSupply',500,'/+3V3')]
    classes='\n'.join(f'    (class {name} {nets} (circuit (use_via "Via[0-1]_700:300_um")) (rule (width {width}) (clearance 200)))' for name,width,nets in groups)
    start=s.index('    (class kicad_default');end=s.index('  (wiring',start)
    path.write_text(s[:start]+classes+'\n  )\n'+s[end:])
elif sys.argv[1]=='import':
    b=k.LoadBoard(str(root/'remote.kicad_pcb'))
    assert k.ImportSpecctraSES(b,str(root/'artifacts/routed.ses'))
    b.BuildConnectivity()
    k.ZONE_FILLER(b).Fill(b.Zones())
    k.SaveBoard(str(root/'remote.kicad_pcb'),b)
