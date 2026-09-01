from __future__ import annotations

import sqlite3
import pytest
from backend.models.base import ProviderError

from backend.agent.context import ContextBuilder
from backend.storage.database import Database
from backend.storage.repository import Repository


def create_session(repository: Repository, title: str = "Новый чат") -> dict:
    return repository.create_session(
        title=title,
        provider="ollama",
        model="test-model",
        system_prompt="Short system contract.",
        context_window=16_384,
        max_output=2_048,
    )


def test_migrations_are_idempotent_and_enable_wal(tmp_path):
    path = tmp_path / "events.db"
    database = Database(path)
    database.initialize()
    database.initialize()
    with sqlite3.connect(path) as connection:
        mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        migrations = connection.execute("SELECT version FROM schema_migrations").fetchall()
    assert mode == "wal"
    assert migrations == [
        ("0001_initial.sql",),
        ("0002_message_sequence.sql",),
        ("0003_tool_calls.sql",),
        ("0004_sandbox_approvals.sql",),
        ("0005_permission_profiles.sql",),
            ("0006_session_trash.sql",),
            ("0007_skills.sql",),
            ("0008_artifacts.sql",),
            ("0009_context_retrieval_vision.sql",),
            ("0010_memory_provenance.sql",),
            ("0011_attachment_uses.sql",),
            ("0012_model_capabilities.sql",),
            ("0013_research.sql",),
        ]


def test_context_builder_never_reads_another_session(tmp_path):
    database = Database(tmp_path / "isolation.db")
    database.initialize()
    repository = Repository(database)
    japan = create_session(repository, "Япония")
    clean = create_session(repository, "Чистый чат")
    repository.create_turn(japan["id"], "Расскажи о Японии")
    repository.create_turn(clean["id"], "Почему небо голубое?")

    context = ContextBuilder(repository).build(clean["id"])
    joined = "\n".join(message["content"] for message in context.messages)

    assert "Почему небо голубое?" in joined
    assert "Япони" not in joined
    assert context.context_window == 16_384


def test_context_budget_keeps_recent_messages_bounded(tmp_path):
    database = Database(tmp_path / "budget.db")
    database.initialize()
    repository = Repository(database)
    session = repository.create_session(
        title="Budget",
        provider="ollama",
        model="test-model",
        system_prompt="System",
        context_window=1_024,
        max_output=128,
    )
    repository.create_turn(session["id"], "x" * 20_000)

    with pytest.raises(ProviderError) as error:
        ContextBuilder(repository).build(session["id"])
    assert error.value.code == "context_limit"
    assert repository.list_context_messages(session["id"])[0]["content"] == "x" * 20_000


def test_restart_marks_inflight_turn_interrupted_and_keeps_event(tmp_path):
    database = Database(tmp_path / "restart.db")
    database.initialize()
    repository = Repository(database)
    session = create_session(repository)
    created = repository.create_turn(session["id"], "Продолжай отвечать")

    count = repository.mark_inflight_interrupted()
    turn = repository.get_turn(created["turn"]["id"])
    events = repository.list_events(turn["id"])

    assert count == 1
    assert turn["status"] == "interrupted"
    assert repository.get_message(turn["assistant_message_id"])["status"] == "failed"
    assert events[-1]["type"] == "turn.interrupted"
