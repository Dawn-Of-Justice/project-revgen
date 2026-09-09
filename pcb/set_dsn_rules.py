from pathlib import Path
p=Path(__file__).resolve().parent/'remote/artifacts/placement.dsn'
s=p.read_text()
s=s.replace('600:300','700:300').replace('(circle F.Cu 600)','(circle F.Cu 700)').replace('(circle B.Cu 600)','(circle B.Cu 700)')
s=s.replace('(width 200)','(width 250)').replace('(clearance 50 (type smd_smd))','(clearance 200 (type smd_smd))')
start=s.index('    (class kicad_default')
groups=[('Signal',250,'AMP_GAIN AMP_SD AMP_SD_SAFE BUTTON I2S_AMP_BCLK I2S_AMP_DIN I2S_AMP_LRC I2S_MIC_SCK I2S_MIC_SD I2S_MIC_WS VBAT_SENSE'),('Power',1000,'VBAT_IN VBAT_SW'),('Speaker',800,'SPK+ "SPK-"'),('Ground',600,'GND'),('LogicSupply',500,'+3V3')]
classes='\n'.join(f'    (class {name} {nets} (circuit (use_via "Via[0-1]_700:300_um")) (rule (width {width}) (clearance 200)))' for name,width,nets in groups)
s=s[:start]+classes+'\n  )\n  (wiring)\n)\n'
p.write_text(s)
print('DSN rules: signals 0.25; power 1.0; speaker 0.8; GND 0.6; 3V3 0.5 mm.')
