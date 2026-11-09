"""Non-blocking single-instance lock, with mandatory Windows byte locks."""
import os
from pathlib import Path


class InstanceLock:
    def __init__(self, directory: Path):
        self.file = None
        try:
            directory.mkdir(parents=True, exist_ok=True)
            self.file = (directory / '.instance.lock').open('a+b')
            # Reading a byte already locked by another process fails on Windows.
            # Stat the file instead, and keep all preparation inside cleanup.
            if os.fstat(self.file.fileno()).st_size == 0:
                self.file.write(b'0')
                self.file.flush()
            self.file.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.close()
            raise RuntimeError(
                'Não foi possível bloquear a pasta de dados. Feche a outra instância '
                'e verifique as permissões de escrita.'
            ) from None

    def close(self):
        if self.file is not None:
            self.file.close()
            self.file = None
