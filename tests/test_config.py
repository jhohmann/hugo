from psycopg.conninfo import conninfo_to_dict

from app import config


def test_database_password_special_characters_need_no_url_encoding(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_HOST", "db")
    monkeypatch.setenv("DB_PASSWORD", "a@b:/ c'\\d")
    parsed = conninfo_to_dict(config.database_url())
    assert parsed["password"] == "a@b:/ c'\\d"
    assert parsed["host"] == "db"


def test_environment_takes_precedence_over_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("DB_HOST=from-file\nDB_PORT=5433\n")
    monkeypatch.setenv("DB_HOST", "from-environment")
    monkeypatch.delenv("DB_PORT", raising=False)
    # Ensure dotenv's modification is restored by monkeypatch after this test.
    monkeypatch.setenv("DB_PORT", "")
    monkeypatch.delenv("DB_PORT")
    config.load_environment(env_file)
    assert conninfo_to_dict(config.database_url())["host"] == "from-environment"
