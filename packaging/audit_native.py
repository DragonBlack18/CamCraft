"""Check app-local MSVC dependencies and video/Tk payload in the onedir build."""
import argparse,json
from pathlib import Path
import pefile

def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    files=[f for f in a.directory.rglob('*') if f.is_file()]
    names={f.name.lower() for f in files}
    required=set();count=0
    for f in files:
        if f.suffix.lower() not in ('.exe','.dll','.pyd'):continue
        try:
            pe=pefile.PE(str(f),fast_load=True)
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
            for row in getattr(pe,'DIRECTORY_ENTRY_IMPORT',[]):
                name=row.dll.decode('ascii').lower()
                if name.startswith(('vcruntime','msvcp','concrt')):required.add(name)
            pe.close();count+=1
        except pefile.PEFormatError:pass
    missing=sorted(required-names)
    checks={'model': 'object_detection_yolox_2022nov.onnx' in names,
            'tkinter': '_tkinter.pyd' in names,
            'python':any(n.startswith('python3') and n.endswith('.dll') for n in names),
            'ffmpeg':any(n.startswith('opencv_videoio_ffmpeg') and n.endswith('.dll') for n in names)}
    report={'pe_files':count,'msvc_required':sorted(required),'missing_app_local_msvc':missing,'payload_checks':checks,'passed':not missing and all(checks.values())}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    if not report['passed']:raise SystemExit('[FAIL] Native payload audit: '+json.dumps(report))
    print('[PASS] Native runtime, MSVC, Tk, FFmpeg and model payload audited.')
if __name__=='__main__':main()
