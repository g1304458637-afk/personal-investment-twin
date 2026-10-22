import os
import stat

import pytest

from src.persistence import LocalRepository
from toujing_core_runtime.chat_archive import ChatArchive


def test_in_memory_repository_does_not_create_a_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repo = LocalRepository(":memory:")
    assert repo.list_accounts() == []
    repo.close()
    assert not (tmp_path / ":memory:").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits")
def test_facts_database_and_wal_are_private_at_creation_and_reopen(tmp_path):
    parent_mode = stat.S_IMODE(tmp_path.stat().st_mode)
    database = tmp_path / "new-private-dir" / "facts.sqlite3"
    repo = LocalRepository(database)
    try:
        assert stat.S_IMODE(database.parent.stat().st_mode) == 0o700
        for suffix in ("", "-wal", "-shm"):
            assert stat.S_IMODE(type(database)(str(database) + suffix).stat().st_mode) == 0o600
    finally:
        repo.close()
    database.chmod(0o644)
    repo = LocalRepository(database)
    repo.close()
    assert stat.S_IMODE(database.stat().st_mode) == 0o600
    assert stat.S_IMODE(tmp_path.stat().st_mode) == parent_mode


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits")
def test_existing_chat_archive_permissions_are_tightened(tmp_path):
    database = tmp_path / "chat.sqlite3"
    database.touch(mode=0o644)
    database.chmod(0o644)
    ChatArchive(database)
    assert stat.S_IMODE(database.stat().st_mode) == 0o600
