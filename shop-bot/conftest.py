"""Test setup: every test gets its own empty shop database and photo folder, so tests never touch your real shop."""
import pytest

import app as server
import config


@pytest.fixture(autouse=True)
def fresh_shop(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_FILE", tmp_path / "shop.db")
    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path / "uploads")
    (tmp_path / "uploads").mkdir()
    for memory in (server._hits, server.login_failures, server.owner_sessions):
        memory.clear()
    server.seen_ids.clear()
    yield
