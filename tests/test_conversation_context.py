"""Real database and chat-service integration; only model responses are mocked."""

from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from app import chat_service, migrate
from app.agent import chat_context
from app.storage import conversation_context, database


@pytest.fixture
def store(monkeypatch):
    try:
        admin = psycopg.connect(database.DATABASE_URL, connect_timeout=2, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL nicht erreichbar")
    name = "test_context_" + uuid4().hex
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    dsn = make_conninfo(database.DATABASE_URL, dbname=name)
    try:
        assert migrate.run_migrations(dsn)["status"] == "ok"
        for module in (database, conversation_context):
            monkeypatch.setattr(module, "get_connection", lambda: psycopg.connect(dsn))
        yield
    finally:
        admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
        admin.close()


def test_chat_service_preserves_transcript_and_reuses_summary(store, monkeypatch):
    monkeypatch.setenv("HUGO_CHAT_HISTORY_TOKENS", "2000")
    cid = database.create_conversation()
    for i in range(12):
        database.save_message(cid, "user" if i % 2 == 0 else "assistant", f"{i}: " + "x" * 700)
    original = database.get_messages(cid)
    summaries, answers = [], []

    def summarize(previous, messages, limit):
        summaries.append(messages)
        return "Ziel ist noch unverbindlich."

    def answer(messages, source):
        answers.append(messages)
        return "Antwort"

    monkeypatch.setattr(chat_context, "summarize", summarize)
    monkeypatch.setattr(chat_service, "ask_hugo", answer)
    assert chat_service.run_chat("Was bleibt offen?", cid)["answer"] == "Antwort"
    chat_service.run_chat("Danke", cid)
    assert len(summaries) == 1
    assert answers[1][0] == answers[0][0]
    assert answers[1][-1] == {"role": "user", "content": "Danke"}
    assert database.get_messages(cid)[:12] == original
    assert len(database.get_messages(cid)) == 16
    assert summaries[0][0]["created_at"].tzinfo is not None
    # A new conversation receives none of another conversation's derived text.
    other = chat_service.run_chat("Neu", None)
    assert other["conversation_id"] != cid
    assert answers[-1] == [{"role": "user", "content": "Neu"}]


def test_summary_is_scoped_monotonic_and_snapshot_safe(store):
    cid, other = database.create_conversation(), database.create_conversation()
    ids = [database.save_message(cid, "user", str(i)) for i in range(4)]
    foreign = database.save_message(other, "user", "Andere Unterhaltung")
    assert not conversation_context.save_summary(cid, foreign, "Falsch", 0)
    assert conversation_context.save_summary(cid, ids[0], "Erster Stand", 0)
    assert conversation_context.save_summary(cid, ids[2], "Neuer Stand", ids[0])
    assert not conversation_context.save_summary(cid, ids[1], "Veraltet", ids[0])
    summary, messages = conversation_context.load_context(cid, ids[3])
    assert summary["content"] == "Neuer Stand"
    assert [m["id"] for m in messages] == [ids[3]]
    # A request whose snapshot predates a newer summary reads original messages.
    summary, messages = conversation_context.load_context(cid, ids[1])
    assert summary is None
    assert [m["id"] for m in messages] == ids[:2]
    summary, messages = conversation_context.load_context(other, foreign)
    assert summary is None and len(messages) == 1
