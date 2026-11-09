"""Windows GUI executable entrypoint. Keep worker diversion before heavy imports."""
from __future__ import annotations
import multiprocessing
import os
import sys
for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(key, "1")


def main() -> int:
    from pathlib import Path
    from vision_app.runtime import TOOLS, default_data_dir
    arguments = sys.argv[1:]
    if arguments[:1] == ['--tool'] and os.environ.get('CAMCRAFT_CHILD_LOG'):
        log = open(os.environ['CAMCRAFT_CHILD_LOG'], 'a', encoding='utf-8', buffering=1)
        sys.stdout = log; sys.stderr = log
    # Windowed apps have stdout/stderr=None. Provide a real stream for dependencies
    # and preserve CLI redirection used by evaluation subprocesses.
    for attr in ('stdout', 'stderr'):
        if getattr(sys, attr) is None:
            setattr(sys, attr, open(os.devnull, 'w', encoding='utf-8'))
    if arguments[:1] == ['--tool']:
        if len(arguments) < 2 or arguments[1] not in TOOLS:
            print('[FAIL] Ferramenta interna desconhecida.', file=sys.stderr)
            return 2
        import importlib
        module = importlib.import_module(TOOLS[arguments[1]])
        sys.argv = [arguments[1], *arguments[2:]]
        return int(module.main() or 0)
    if arguments[:1] == ['--self-test']:
        from vision_app.selftest import main as selftest_main
        return selftest_main(arguments[1:])
    from run import main as desktop_main
    return int(desktop_main(arguments) or 0)


if __name__ == '__main__':
    # In a frozen Windows application this prevents recursive window/process spawn.
    for stream in ("stdout", "stderr"):
        if getattr(sys, stream) is None:
            setattr(sys, stream, open(os.devnull, "w", encoding="utf-8"))
    multiprocessing.freeze_support()
    raise SystemExit(main())
