"""Package checked A3 exports and record reproducible file hashes."""
from pathlib import Path
import hashlib
import json
import zipfile
root=Path(__file__).resolve().parent/'remote'
drc=json.loads((root/'artifacts/final-drc.json').read_text())
assert not any(drc[key] for key in ('violations','unconnected_items','schematic_parity'))
fabrication=sorted((root/'manufacturing').iterdir())
assert len(fabrication)==10
with zipfile.ZipFile(root/'RevGen-Remote-A3-Gerbers.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in fabrication:z.write(p,p.name)
source=[root/name for name in ['remote.kicad_pcb','remote.kicad_sch','remote.kicad_pro','fp-lib-table','ASSEMBLY.md','A3_CORRECTIONS.md','A2_FRESH_REVIEW.md']]
source+=sorted((root/'revgen.pretty').glob('*.kicad_mod'))
with zipfile.ZipFile(root/'RevGen-Remote-A3-KiCad.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in source:z.write(p,p.relative_to(root).as_posix())
for filename,files in [('RevGen-Remote-A3-Gerbers.zip',fabrication),('RevGen-Remote-A3-KiCad.zip',source)]:
    with zipfile.ZipFile(root/filename) as z:
        for p in files:assert z.read(p.name if filename.endswith('Gerbers.zip') else p.relative_to(root).as_posix())==p.read_bytes()
manifest=json.loads((root/'artifacts/release-manifest.json').read_text())
manifest.update(revision='A3 prototype',supersedes='A2 reflected amplifier mounting; A1 rejected',review='../A3_CORRECTIONS.md',amplifier_mounting='Component side UP; verified against manufacturer Eagle geometry',open_software_issue='24 kHz TTS playback outside MAX98357A specified rate bands')
files=source+fabrication+[root/'RevGen-Remote-A3-Gerbers.zip',root/'RevGen-Remote-A3-KiCad.zip',root/'artifacts/firmware-validation.txt',root/'artifacts/remote-top.png',root/'artifacts/assembly-1to1.svg',root/'artifacts/final-drc.json',root/'artifacts/erc.txt']
manifest['sha256']={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
firmware=root/'../../firmware/remote/remote.ino'
manifest['sha256']['../../firmware/remote/remote.ino']=hashlib.sha256(firmware.read_bytes()).hexdigest()
(root/'artifacts/release-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('A3 Gerber and KiCad archives verified byte for byte; release manifest updated.')
