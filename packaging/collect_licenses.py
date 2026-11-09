"""Bundle dependency notices and exact versions without collecting user data."""
from pathlib import Path
import hashlib
import importlib.metadata as metadata
import json
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.build_assets'

def main():
    OUT.mkdir(exist_ok=True)
    dest=OUT/'licenses';dest.mkdir(exist_ok=True)
    for path in (ROOT/'licenses').glob('*'):
        if path.is_file():shutil.copy2(path,dest/path.name)
    shutil.copy2(ROOT/'LICENSE',dest/'CamCraft-MIT.txt')
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if not python_license.exists():raise RuntimeError('Python redistribution license not found')
    shutil.copy2(python_license,dest/'Python-LICENSE.txt')
    distributions=[]
    for d in sorted(metadata.distributions(),key=lambda d:d.metadata.get('Name','').lower()):
        name=d.metadata.get('Name','unknown')
        folder=dest/name
        collected=[]
        for entry in d.files or []:
            text=str(entry).lower()
            if any(token in text for token in ('license','copying','notice')) and '..' not in Path(entry).parts:
                path=Path(d.locate_file(entry))
                if path.is_file() and path.stat().st_size<4*1024**2:
                    target=folder/str(entry).replace('\\','/')
                    target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(path,target);collected.append(str(target.relative_to(dest)))
        distributions.append({'name':name,'version':d.version,'licenses':collected})
    tcl=Path(sys.base_prefix)/'tcl'
    for file in tcl.rglob('license.terms'):
        target=dest/'Tcl-Tk'/file.relative_to(tcl);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,target)
    (OUT/'runtime-manifest.json').write_text(json.dumps({'python':sys.version,
        'build_distributions':distributions,'note':'Includes build-only packages; not an SPDX certification.'},indent=2),encoding='utf-8')
    print('[PASS] Third-party licenses and exact environment manifest collected.')
if __name__=='__main__':main()
