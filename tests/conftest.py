import os
import pytest

# Tests sollen keinen echten OpenAI-Zugang benötigen.
os.environ.setdefault("OPENAI_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    """Unit tests use environment defaults, never the user's saved preferences."""
    from app.storage import settings
    monkeypatch.setattr(settings, "read_settings", lambda: {"values": {}, "revision": 0, "updated_at": None})

    def reject_write(*args, **kwargs):
        raise AssertionError("Settings writes need an isolated test store")
    monkeypatch.setattr(settings, "save_settings", reject_write)
