from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.agent.contracts import AgentLimits, AgentResult, AgentTaskSpec
from backend.agent.heartbeat import AgentHeartbeatService
from backend.agent.history_search import HistorySearch
from backend.agent.orchestrator import AgentOrchestrator
from backend.agent.task_store import AgentTaskStore
from backend.storage.database import Database
from backend.storage.repository import Repository
from backend.tools.contracts import ToolContext, ToolInput
from backend.tools.discovery import ToolSearchTool
from backend.tools.registry import ToolRegistry


def db(tmp_path: Path) -> Database:
    value = Database(tmp_path / "history.sqlite3")
    value.initialize()
    return value


def session(repository: Repository) -> dict:
    return repository.create_session(title="Test", provider="ollama", model="model", system_prompt="", context_window=4096, max_output=512)


class _Executor:
    gateway = SimpleNamespace(registry=None)

    async def run(self, task_id: str) -> AgentResult:
        return AgentResult(task_id, "completed", "done", [], [], [], {"steps": 1, "tool_calls": 0, "input_tokens": 1, "output_tokens": 1})


def _orchestrator(database: Database, repository: Repository, tools: ToolRegistry) -> tuple[AgentOrchestrator, AgentTaskStore]:
    store = AgentTaskStore(database)
    return AgentOrchestrator(store, repository, _Executor(), tools), store


def test_agent_limits_apply_profile_overrides_and_absolute_caps(tmp_path: Path):
    database = db(tmp_path)
    store = AgentTaskStore(database)
    store.save_settings(enabled=True, profile="conservative", overrides={"max_children": 99, "max_steps": 20, "unknown": 1})
    limits = AgentOrchestrator(store, Repository(database), _Executor(), ToolRegistry([])).limits()
    assert limits.max_children == 32
    assert limits.max_steps == 20


@pytest.mark.asyncio
async def test_delegation_intersects_allowlist_and_routes_by_role_and_creates_background_watch(tmp_path: Path):
    database = db(tmp_path)
    repository = Repository(database)
    current = session(repository)
    root_turn_id = repository.create_turn(current["id"], "root")["turn"]["id"]
    tools = ToolRegistry([])
    heartbeat = AgentHeartbeatService(database, AgentTaskStore(database))
    orchestrator, store = _orchestrator(database, repository, tools)
    orchestrator.heartbeats = heartbeat
    store.save_settings(enabled=True, profile="balanced", overrides={}, role_routes={"research": {"model": "research-model"}})
    # The registry is deliberately empty: unknown names must not leak into a child policy.
    result = await orchestrator.delegate(session_id=current["id"], root_turn_id=root_turn_id, parent_task_id=None,
        specs=[AgentTaskSpec("look", {}, role="research", allowed_tools=["missing"])], background=True)
    task = store.get(result["task_ids"][0])
    assert task["allowed_tools"] == []
    assert task["model"] == "research-model"
    assert heartbeat.for_session(current["id"])["watches"]
    await orchestrator.shutdown()


def test_task_activity_touch_does_not_mutate_last_activity_for_non_running_task(tmp_path: Path):
    database = db(tmp_path)
    repository = Repository(database)
    current = session(repository)
    root_turn_id = repository.create_turn(current["id"], "root")["turn"]["id"]
    store = AgentTaskStore(database)
    task = store.create(session_id=current["id"], root_turn_id=root_turn_id, parent_task_id=None, ordinal=0, depth=1,
        spec=AgentTaskSpec("x", {}), provider_profile_id=None, model="m", permission_profile="standard",
        allowed_tools=[], limits=AgentLimits(1, 1, 1, 1, 1, 1, 1, 1, 1, 1))
    before = store.get(task["id"])["last_activity_at"]
    store.touch_activity(task["id"], "ignored")
    assert store.get(task["id"])["last_activity_at"] == before


def test_restart_reconcile_emits_terminal_heartbeat_event_and_acknowledges(tmp_path: Path):
    database = db(tmp_path)
    repository = Repository(database)
    current = session(repository)
    root_turn_id = repository.create_turn(current["id"], "root")["turn"]["id"]
    store = AgentTaskStore(database)
    task = store.create(session_id=current["id"], root_turn_id=root_turn_id, parent_task_id=None, ordinal=0, depth=1,
        spec=AgentTaskSpec("x", {}), provider_profile_id=None, model="m", permission_profile="standard",
        allowed_tools=[], limits=AgentLimits(1, 1, 1, 1, 1, 1, 1, 1, 1, 1), execution_mode="background")
    heartbeat = AgentHeartbeatService(database, store)
    heartbeat.ensure_watch(task["id"])
    store.set_running(task["id"])
    store.finish(task["id"], status="completed", result={})
    assert heartbeat.reconcile_after_restart() == 1
    # A terminal watch is closed atomically, so a second startup reconciliation
    # cannot emit the same completion notification again.
    assert heartbeat.reconcile_after_restart() == 0
    events = heartbeat.for_session(current["id"])["events"]
    assert len(events) == 1
    assert events[0]["type"] == "completed"
    assert heartbeat.acknowledge(events[0]["id"])["acknowledged_at"]


def test_tool_search_is_bounded_to_allowlist_and_validates_input(tmp_path: Path):
    class Tool:
        name = "fs.read"
        title = "Read files"
        description = "Read project files"
        annotations = {}
        input_model = ToolInput

        def definition(self):
            return {"name": self.name, "title": self.title, "description": self.description, "annotations": self.annotations, "input_schema": {}}

    registry = ToolRegistry([Tool()])
    search = ToolSearchTool(registry)
    context = ToolContext(session_id="s", turn_id="t", allowed_tool_names={"fs.read"})
    result = asyncio.run(search.execute(context, search.input_model.model_validate({"query": "read"})))
    assert [item["name"] for item in result.output["matches"]] == ["fs.read"]
    with pytest.raises(ValueError):
        search.input_model.model_validate({"query": " "})


def test_history_fts_backfill_update_delete_snippet_cap_and_trash_exclusion(tmp_path: Path):
    database = db(tmp_path)
    repository = Repository(database)
    current = session(repository)
    created = repository.create_turn(current["id"], "needle original")
    repository.append_assistant_delta(created["assistant_message"]["id"], "needle " + "x" * 600)
    repository.append_assistant_delta(created["assistant_message"]["id"], " streamingtoken")
    search = HistorySearch(database)
    assert search.search("needle")[0]["message_id"] == created["user_message"]["id"]
    streamed = search.search("streamingtoken")
    assert [item["message_id"] for item in streamed] == [created["assistant_message"]["id"]]
    assert len(search.search("needle")[0]["snippet"]) <= 500
    with database.transaction() as connection:
        connection.execute("DELETE FROM messages WHERE id=?", (created["user_message"]["id"],))
    assert all(item["message_id"] != created["user_message"]["id"] for item in search.search("needle"))
    trashed = session(repository)
    turn = repository.create_turn(trashed["id"], "private needle")
    repository.set_turn_status(turn["turn"]["id"], "completed", finished=True)
    repository.trash_session(trashed["id"])
    assert all(item["session_id"] != trashed["id"] for item in search.search("needle"))
    with pytest.raises(ValueError):
        search.search("!@#$")
    with pytest.raises(ValueError):
        search.search("a" * 301)


def test_history_fts_migration_backfills_messages_created_before_stage20(tmp_path: Path):
    migration_dir = tmp_path / "migrations"
    shutil.copytree(Path("backend/storage/migrations"), migration_dir,
                    ignore=shutil.ignore_patterns("0025_history_heartbeat.sql"))
    database = Database(tmp_path / "backfill.sqlite3", migration_dir)
    database.initialize()
    repository = Repository(database)
    current = session(repository)
    repository.create_turn(current["id"], "backfilled phrase")
    Database(database.path).initialize()
    assert HistorySearch(Database(database.path)).search("backfilled")[0]["session_id"] == current["id"]


def test_database_backup_retains_five_and_recovery_preserves_primary_wal_shm(tmp_path: Path):
    database = db(tmp_path)
    for index in range(7):
        database.create_backup(f"test{index}")
    assert len(list(database.backup_dir.glob("*.sqlite3"))) == 5
    backup = sorted(database.backup_dir.glob("*.sqlite3"), key=lambda item: item.stat().st_mtime, reverse=True)[0]
    primary = database.path
    primary.write_bytes(b"not sqlite")
    wal = Path(f"{primary}-wal")
    shm = Path(f"{primary}-shm")
    wal.write_bytes(b"wal-companion")
    shm.write_bytes(b"shm-companion")
    recovered = Database(primary)
    recovered.initialize()
    assert recovered.recovery_report["status"] == "restored"
    assert recovered.recovery_report["restored_from"] == backup.name
    assert all((primary.parent / name).exists() for name in recovered.recovery_report["preserved_files"])
    assert recovered.quick_check(primary)[0]


def test_database_corruption_fails_closed_without_valid_backup(tmp_path: Path):
    path = tmp_path / "no-recovery.sqlite3"
    path.write_bytes(b"corrupt")
    with pytest.raises(RuntimeError, match="no valid recovery backup"):
        Database(path).initialize()
    assert path.read_bytes() == b"corrupt"
