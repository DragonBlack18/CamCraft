"""Verify the distributed source snapshot. Generated data/.venv files are not checked."""
import hashlib,json,sys
from pathlib import Path

def main():
    root=Path(__file__).resolve().parents[1]
    try:
        doc=json.loads((root/'MANIFEST.sha256.json').read_text(encoding='utf-8'))
        errors=[]
        for name,expected in doc['files'].items():
            p=root/name
            if root not in p.resolve().parents or not p.is_file() or p.is_symlink():errors.append(name);continue
            h=hashlib.sha256()
            with p.open('rb') as f:
                for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
            if h.hexdigest()!=expected:errors.append(name)
        if errors:
            print('[FAIL] Ausentes/alterados: '+', '.join(errors));return 1
        print('[PASS] SHA-256 conferido em '+str(len(doc['files']))+' arquivos distribuídos. Não autentica o autor do pacote.');return 0
    except (OSError,ValueError,KeyError) as exc:print('[FAIL] '+str(exc));return 1
if __name__=='__main__':raise SystemExit(main())
