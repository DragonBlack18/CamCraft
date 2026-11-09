import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json,platform,struct,importlib.metadata
import cv2,numpy,scipy,PIL,pydantic,psutil,tkinter
from vision_app.model import verified,MODEL_FILE

def main():
    report={'python':sys.version.split()[0],'platform':platform.platform(),'bits':struct.calcsize('P')*8,
    'opencv':cv2.__version__,'numpy':numpy.__version__,'scipy':scipy.__version__,'Pillow':PIL.__version__,
    'pydantic':pydantic.__version__,'psutil':psutil.__version__,'Tk':tkinter.TkVersion,
    'model_verified':verified(Path(__file__).resolve().parents[1]/'models'/MODEL_FILE),
    'gui_importable':True,'camera_tested':False,'gpu_used':False}
    print(json.dumps(report,indent=2))
    conflicts=[]
    for name in ('opencv-python','opencv-contrib-python','opencv-contrib-python-headless'):
        try:importlib.metadata.version(name);conflicts.append(name)
        except importlib.metadata.PackageNotFoundError:pass
    if conflicts:print('[FAIL] Mais de uma distribuição cv2 no ambiente: '+', '.join(conflicts));return 1
    if report['bits']!=64:print('[FAIL] Use Python x64.');return 1
    print('[PASS] Bibliotecas importadas. Isto não homologa a câmera física.');return 0
if __name__=='__main__':raise SystemExit(main())
