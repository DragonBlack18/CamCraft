# Build on Windows x64 only. CAMCRAFT_BUNDLE_MODE selects onedir/onefile.
from pathlib import Path
import os
import sys
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent.resolve()
sys.path.insert(0, str(ROOT))
from vision_app.model import MODEL_FILE, MODEL_SHA256, verified
from vision_app.runtime import VERSION
if sys.platform != 'win32':
    raise RuntimeError('Build Windows executables on a Windows runner.')
if not verified(ROOT/'models'/MODEL_FILE):
    raise RuntimeError('Verified model is mandatory; refusing an incomplete executable. Expected '+MODEL_SHA256)
mode = os.environ.get('CAMCRAFT_BUNDLE_MODE', 'onedir')
if mode not in ('onedir','onefile'):
    raise RuntimeError('Unknown bundle mode')
assets = ROOT/'.build_assets'
if not (assets/'licenses').is_dir():
    raise RuntimeError('Run packaging/collect_licenses.py before freezing')
datas = [(str(ROOT/'models'/MODEL_FILE), 'models'),
         (str(ROOT/'models'/'manifest.json'), 'models'),
         (str(ROOT/'LICENSE'), '.'),
         (str(ROOT/'THIRD_PARTY_NOTICES.md'), '.'),
         (str(ROOT/'docs'/'WINDOWS.md'), 'docs'),
         (str(assets/'licenses'), 'licenses'),
         (str(assets/'runtime-manifest.json'), '.')]
for dependency in ('opencv-python-headless','numpy','scipy','Pillow','pydantic','pydantic_core','psutil'):
    datas += copy_metadata(dependency)
hidden = collect_submodules('vision_app') + [
    'tools.validate_dataset', 'tools.import_previous', 'tools.restore_backup',
    'multiprocessing.popen_spawn_win32', 'multiprocessing.spawn', 'tkinter.messagebox',
    'tkinter.filedialog', 'tkinter.ttk', 'PIL.ImageTk', 'scipy.optimize._lsap']
a = Analysis([str(ROOT/'camcraft_launcher.py')], pathex=[str(ROOT)],
    binaries=[], datas=datas, hiddenimports=hidden, hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=['pytest','IPython','notebook','matplotlib','pandas',
    'torch','tensorflow','PyQt5','PyQt6','PySide2','PySide6'], noarchive=False)
pyz = PYZ(a.pure)
options = dict(debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    icon=str(ROOT/'assets'/'camcraft.ico'), version=str(ROOT/'packaging'/'version_info.txt'))
if mode == 'onefile':
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
        name='CamCraft-Portable-'+VERSION+'-x64', **options)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='CamCraft', **options)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='CamCraft')
