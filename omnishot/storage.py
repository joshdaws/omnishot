"""Replace saved artifacts only after a complete sibling file is ready."""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile


@contextmanager
def atomic_output(destination):
    destination=Path(destination)
    fd,name=tempfile.mkstemp(prefix=".omnishot-",suffix=destination.suffix,dir=destination.parent)
    os.close(fd);temporary=Path(name)
    try:
        yield temporary
        with temporary.open("rb") as stream:os.fsync(stream.fileno())
        temporary.replace(destination)
    finally:temporary.unlink(missing_ok=True)
