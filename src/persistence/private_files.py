"""Private local SQLite files without changing unrelated parent directories."""
from __future__ import annotations

import os
from pathlib import Path


def prepare_private_database(path: Path) -> None:
    if str(path) == ":memory:":
        return
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # SQLite must not create its first page at the process umask (often 0644).
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if os.name == "posix":
            os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)
    restrict_database_files(path)


def restrict_database_files(path: Path) -> None:
    if os.name != "posix" or str(path) == ":memory:":
        return
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm"), Path(f"{path}-journal")):
        try:
            candidate.chmod(0o600)
        except FileNotFoundError:
            pass  # WAL/journal files are created and removed by SQLite.
