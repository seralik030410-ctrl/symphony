import sqlite3

import pytest

from backend.sandbox.policy import PolicyEngine
from backend.storage.database import Database
from backend.tools.contracts import ToolContext, ToolError
from backend.tools.files import WriteFileTool
from backend.tools.registry import ToolRegistry
from backend.tools.snapshots import SnapshotStore
from backend.tools.workspace import WorkspaceManager
from backend.agent.turn_service import TurnService
from test_sandbox_policy import shell_tool


def test_migration_rollback_keeps_version_and_ddl_atomic(tmp_path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001.sql").write_text("CREATE TABLE example(id INTEGER); INVALID SQL;", encoding="utf-8")
    db = Database(tmp_path / "test.db", migrations)
    with pytest.raises(sqlite3.OperationalError):
        db.initialize()
    with db.read() as connection:
        assert connection.execute("SELECT * FROM schema_migrations").fetchall() == []
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='example'").fetchall() == []
    (migrations / "001.sql").write_text("CREATE TABLE example(id INTEGER);", encoding="utf-8")
    db.initialize()


def test_profiles_enforce_writes_and_unknown_commands(tmp_path):
    engine = PolicyEngine()
    write = WriteFileTool(WorkspaceManager(tmp_path / "workspace"))
    for profile in ("read_only", "full_manual"):
        assert engine.evaluate(write, {}, profile=profile).action == "approval_required"
    for profile in ("project_edit", "build"):
        assert engine.evaluate(write, {}, profile=profile).action == "allow"
    for command in ("npm test; rm a.txt", "npm test $(curl bad)", "python -c 'print(1)'", "sh script.sh", "npm test > file"):
        assert engine.evaluate(shell_tool(tmp_path), {"command": command}, profile="build").action == "approval_required"
    assert engine.evaluate(write, {}, profile="typo").action == "deny"


async def test_snapshots_restore_and_keep_safety_copy_across_instances(tmp_path):
    manager = WorkspaceManager(tmp_path / "workspaces")
    registry = ToolRegistry.stage_two(manager)
    context = ToolContext("a" * 32, "b" * 32)
    await registry.execute("fs.write", {"path": "src/a.txt", "content": "before"}, context)
    result = await registry.execute("fs.write", {"path": "src/a.txt", "content": "after", "overwrite": True}, context)
    await registry.execute("fs.write", {"path": "new.txt", "content": "keep me"}, context)
    store = SnapshotStore(WorkspaceManager(manager.root))
    safety = store.create(context.session_id, context.turn_id, "restore")
    assert set(store.restore(context.session_id, result.output["snapshot_id"])) == {"src/a.txt", "new.txt"}
    assert manager.resolve(context.session_id, "src/a.txt").read_text() == "before"
    store.restore(context.session_id, safety["id"])
    assert manager.resolve(context.session_id, "new.txt").read_text() == "keep me"
    with pytest.raises(ToolError, match="does not belong"):
        store.restore("c" * 32, safety["id"])
    assert not (manager.session_root(context.session_id) / "snapshots").exists()


async def test_snapshot_budget_fails_before_write(tmp_path, monkeypatch):
    manager = WorkspaceManager(tmp_path / "workspaces")
    registry = ToolRegistry.stage_two(manager)
    context = ToolContext("a" * 32, "b" * 32)
    path = manager.resolve(context.session_id, "source.txt")
    path.write_text("original")
    monkeypatch.setattr(SnapshotStore, "MAX_BYTES", 1)
    with pytest.raises(ToolError, match="not run"):
        await registry.execute("fs.write", {"path": "source.txt", "content": "lost", "overwrite": True}, context)
    assert path.read_text() == "original"


async def test_active_turn_permissions_are_frozen(client, adapters):
    session = (await client.post("/api/sessions", json={})).json()
    assert session["policy_profile"] == "build"
    assert session["context_window"] == 16384
    adapter = adapters["ollama"]
    adapter.pause_after_first = True
    adapter.release.clear()
    created = (await client.post(f"/api/sessions/{session['id']}/turns", json={"content": "hello"})).json()
    await adapter.first_chunk_sent.wait()
    response = await client.patch(f"/api/sessions/{session['id']}", json={"policy_profile": "full_manual"})
    assert response.status_code == 409
    assert adapter.requests[-1].context_window == 16384
    await client.post(f"/api/turns/{created['turn']['id']}/cancel")


async def test_preview_has_opaque_origin_sandbox(client, app):
    session = (await client.post("/api/sessions", json={})).json()
    app.state.runtime.workspaces.resolve(session["id"], "index.html").write_text("<h1>test</h1>")
    response = await client.get(f"/api/sessions/{session['id']}/preview/index.html")
    assert "sandbox allow-scripts;" in response.headers["content-security-policy"]
    assert "allow-same-origin" not in response.headers["content-security-policy"]
    assert response.headers["access-control-allow-origin"] == "*"


def test_model_observations_do_not_repeat_write_diff():
    import json
    observation = {"ok": True, "diff": "x" * 50000, "output": {"path": "a.txt"}}
    compact = json.loads(TurnService._model_observation(observation))
    assert "diff" not in compact
    observation = {"ok": True, "output": {"stdout": "x" * 50000}}
    assert json.loads(TurnService._model_observation(observation))["truncated"] is True
