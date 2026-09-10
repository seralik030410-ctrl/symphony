from __future__ import annotations

import json
import uuid
from typing import Any

from backend.agent.contracts import AgentCommandType, AgentExecutionMode, AgentLimits, AgentTaskSpec
from backend.storage.database import Database, utc_now


class AgentTaskStore:
    def __init__(self, database: Database, *, lazy_tools_default: bool = True) -> None:
        self.database = database
        self.lazy_tools_default = lazy_tools_default

    def settings(self) -> dict[str, Any]:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM agent_settings WHERE id=1").fetchone()
        if not row:
            return {"enabled": True, "profile": "balanced", "overrides": {},
                    "lazy_tools_enabled": self.lazy_tools_default, "role_routes": {}}
        value = dict(row)
        return {"enabled": bool(value["enabled"]), "profile": value["profile"],
                "overrides": json.loads(value["overrides_json"]),
                "lazy_tools_enabled": bool(value.get("lazy_tools_enabled", 1)),
                "role_routes": json.loads(value.get("role_routes_json") or "{}")}

    def save_settings(self, *, enabled: bool, profile: str, overrides: dict[str, Any],
                      lazy_tools_enabled: bool = True,
                      role_routes: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO agent_settings(id,enabled,profile,overrides_json,updated_at,lazy_tools_enabled,role_routes_json) VALUES(1,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET enabled=excluded.enabled,profile=excluded.profile,"
                "overrides_json=excluded.overrides_json,updated_at=excluded.updated_at,"
                "lazy_tools_enabled=excluded.lazy_tools_enabled,role_routes_json=excluded.role_routes_json",
                (int(enabled), profile, json.dumps(overrides), utc_now(), int(lazy_tools_enabled),
                 json.dumps(role_routes or {}, ensure_ascii=False)),
            )
        return self.settings()

    def create(self, *, session_id: str, root_turn_id: str, parent_task_id: str | None,
               ordinal: int, depth: int, spec: AgentTaskSpec, provider_profile_id: str | None,
               model: str, permission_profile: str, allowed_tools: list[str], limits: AgentLimits,
               execution_mode: AgentExecutionMode = "foreground") -> dict[str, Any]:
        task_id = str(uuid.uuid4())
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO agent_tasks(
                    id,session_id,root_turn_id,parent_task_id,ordinal,depth,goal,context_json,
                    provider_profile_id,model,status,permission_profile,allowed_tools_json,
                    output_schema_json,max_steps,max_tool_calls,max_input_tokens,max_output_tokens,
                    deadline_seconds,created_at,execution_mode,last_activity_at,activity_phase,role
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (task_id, session_id, root_turn_id, parent_task_id, ordinal, depth, spec.goal,
                 json.dumps(spec.context, ensure_ascii=False), provider_profile_id, model, "queued",
                 permission_profile, json.dumps(allowed_tools),
                 json.dumps(spec.output_schema) if spec.output_schema else None,
                 limits.max_steps, limits.max_tool_calls, limits.max_input_tokens,
                 limits.max_output_tokens, limits.deadline_seconds, now, execution_mode, now, "queued", spec.role),
            )
        self.append_event(task_id, "agent.queued", {
            "goal": spec.goal, "depth": depth, "ordinal": ordinal, "role": spec.role,
            "provider_profile_id": provider_profile_id, "model": model})
        return self.get(task_id)

    def get(self, task_id: str) -> dict[str, Any]:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise KeyError(task_id)
        return self._decode(dict(row))

    def list_tree(self, root_turn_id: str) -> list[dict[str, Any]]:
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_tasks WHERE root_turn_id=? ORDER BY depth, parent_task_id, ordinal, created_at",
                (root_turn_id,),
            ).fetchall()
        return [self._decode(dict(row)) for row in rows]

    def active_for_session(self, session_id: str) -> list[dict[str, Any]]:
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_tasks WHERE session_id=? AND status IN ('queued','running') "
                "ORDER BY created_at, depth, ordinal",
                (session_id,),
            ).fetchall()
        return [self._decode(dict(row)) for row in rows]

    def list_descendants(self, task_id: str) -> list[dict[str, Any]]:
        self.get(task_id)
        with self.database.read() as connection:
            rows = connection.execute(
                """WITH RECURSIVE descendants(id) AS (
                SELECT id FROM agent_tasks WHERE parent_task_id=?
                UNION ALL
                SELECT child.id FROM agent_tasks child
                JOIN descendants parent ON child.parent_task_id=parent.id
                )
                SELECT task.* FROM agent_tasks task
                JOIN descendants item ON item.id=task.id
                ORDER BY task.depth, task.parent_task_id, task.ordinal, task.created_at""",
                (task_id,),
            ).fetchall()
        return [self._decode(dict(row)) for row in rows]

    def count_tree(self, root_turn_id: str) -> int:
        with self.database.read() as connection:
            row = connection.execute("SELECT COUNT(*) n FROM agent_tasks WHERE root_turn_id=?", (root_turn_id,)).fetchone()
        return int(row["n"])

    def set_running(self, task_id: str) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute("UPDATE agent_tasks SET status='running',started_at=?,last_activity_at=?,activity_phase='starting',stalled_at=NULL WHERE id=? AND status='queued'",
                               (now, now, task_id))
        self.append_event(task_id, "agent.started", {})

    def finish(self, task_id: str, *, status: str, result: dict[str, Any] | None = None,
               error: str | None = None, usage: dict[str, int] | None = None) -> dict[str, Any]:
        usage = usage or {}
        now = utc_now()
        already_terminal = False
        with self.database.transaction() as connection:
            current = connection.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
            if not current:
                raise KeyError(task_id)
            if current["status"] in {"completed", "failed", "cancelled", "interrupted"}:
                already_terminal = True
            else:
                connection.execute(
                    """UPDATE agent_tasks SET status=?,result_json=?,error=?,finished_at=?,
                    used_steps=?,used_tool_calls=?,used_input_tokens=?,used_output_tokens=?,
                    last_activity_at=?,activity_phase='finished',stalled_at=NULL WHERE id=?""",
                    (status, json.dumps(result, ensure_ascii=False) if result is not None else None, error,
                     now, usage.get("steps", 0), usage.get("tool_calls", 0),
                     usage.get("input_tokens", 0), usage.get("output_tokens", 0), now, task_id),
                )
                if current["execution_mode"] == "background":
                    connection.execute(
                        "INSERT OR IGNORE INTO agent_completion_receipts(id,task_id,session_id,root_turn_id,status,created_at) VALUES(?,?,?,?,?,?)",
                        (str(uuid.uuid4()), task_id, current["session_id"], current["root_turn_id"], status, now),
                    )
                connection.execute(
                    "UPDATE agent_task_commands SET status='rejected',rejection_reason='Task finished before command could be applied',applied_at=? WHERE task_id=? AND status IN ('queued','delivered')",
                    (now, task_id),
                )
        if not already_terminal:
            self.append_event(task_id, f"agent.{status}", {"error": error} if error else {})
        return self.get(task_id)

    def queue_command(self, task_id: str, command_type: AgentCommandType,
                      payload: dict[str, Any]) -> dict[str, Any]:
        if command_type not in {"steer", "stop"}:
            raise ValueError("Unsupported agent command")
        encoded = json.dumps(payload, ensure_ascii=False)
        if len(encoded.encode("utf-8")) > 32_768:
            raise ValueError("Agent command is too large")
        now = utc_now()
        with self.database.transaction() as connection:
            task = connection.execute("SELECT status FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
            if not task:
                raise KeyError(task_id)
            if task["status"] in {"completed", "failed", "cancelled", "interrupted"}:
                raise ValueError("Agent task is already finished")
            row = connection.execute("SELECT COALESCE(MAX(sequence),0)+1 n FROM agent_task_commands WHERE task_id=?", (task_id,)).fetchone()
            sequence = int(row["n"])
            command_id = str(uuid.uuid4())
            connection.execute(
                "INSERT INTO agent_task_commands(id,task_id,sequence,type,payload_json,status,created_at) VALUES(?,?,?,?,?,'queued',?)",
                (command_id, task_id, sequence, command_type, encoded, now),
            )
        self.append_event(task_id, "agent.command_queued", {"command_id": command_id, "type": command_type})
        return self.get_command(command_id)

    def commands(self, task_id: str, after: int = 0) -> list[dict[str, Any]]:
        self.get(task_id)
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_task_commands WHERE task_id=? AND sequence>? ORDER BY sequence",
                (task_id, after),
            ).fetchall()
        return [self._decode_command(dict(row)) for row in rows]

    def claim_steering(self, task_id: str) -> list[dict[str, Any]]:
        now = utc_now()
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_task_commands WHERE task_id=? AND type='steer' AND status='queued' ORDER BY sequence",
                (task_id,),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if ids:
                marks = ",".join("?" for _ in ids)
                connection.execute(f"UPDATE agent_task_commands SET status='delivered',delivered_at=? WHERE id IN ({marks}) AND status='queued'", [now, *ids])
        return [self._decode_command(dict(row) | {"status": "delivered", "delivered_at": now}) for row in rows]

    def apply_command(self, command_id: str) -> dict[str, Any]:
        with self.database.transaction() as connection:
            connection.execute("UPDATE agent_task_commands SET status='applied',applied_at=? WHERE id=? AND status IN ('queued','delivered')", (utc_now(), command_id))
        return self.get_command(command_id)

    def reject_command(self, command_id: str, reason: str) -> dict[str, Any]:
        with self.database.transaction() as connection:
            connection.execute("UPDATE agent_task_commands SET status='rejected',rejection_reason=?,applied_at=? WHERE id=? AND status IN ('queued','delivered')", (reason[:500], utc_now(), command_id))
        return self.get_command(command_id)

    def touch_activity(self, task_id: str, phase: str, detail: dict[str, Any] | None = None) -> None:
        resumed = False
        with self.database.transaction() as connection:
            current = connection.execute("SELECT stalled_at FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
            resumed = bool(current and current["stalled_at"])
            connection.execute(
                "UPDATE agent_tasks SET last_activity_at=?,activity_phase=?,activity_json=?,stalled_at=NULL WHERE id=? AND status='running'",
                (utc_now(), phase[:80], json.dumps(detail or {}, ensure_ascii=False), task_id),
            )
        if resumed:
            self.append_event(task_id, "agent.activity_resumed", {})

    def mark_stalled(self, task_id: str) -> bool:
        now = utc_now()
        with self.database.transaction() as connection:
            cursor = connection.execute("UPDATE agent_tasks SET stalled_at=? WHERE id=? AND status='running' AND stalled_at IS NULL", (now, task_id))
        if cursor.rowcount:
            self.append_event(task_id, "agent.stalled", {})
        return bool(cursor.rowcount)

    def clear_stalled(self, task_id: str) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute("UPDATE agent_tasks SET stalled_at=NULL WHERE id=? AND stalled_at IS NOT NULL", (task_id,))
        if cursor.rowcount:
            self.append_event(task_id, "agent.activity_resumed", {})
        return bool(cursor.rowcount)

    def running(self) -> list[dict[str, Any]]:
        with self.database.read() as connection:
            rows = connection.execute("SELECT * FROM agent_tasks WHERE status='running'").fetchall()
        return [self._decode(dict(row)) for row in rows]

    def background_for_session(self, session_id: str) -> dict[str, Any]:
        with self.database.read() as connection:
            tasks = connection.execute("SELECT * FROM agent_tasks WHERE session_id=? AND execution_mode='background' AND status IN ('queued','running') ORDER BY created_at", (session_id,)).fetchall()
            receipts = connection.execute("SELECT * FROM agent_completion_receipts WHERE session_id=? AND acknowledged_at IS NULL ORDER BY created_at", (session_id,)).fetchall()
        return {"tasks": [self._decode(dict(row)) for row in tasks], "receipts": [dict(row) for row in receipts]}

    def acknowledge_receipt(self, receipt_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute("UPDATE agent_completion_receipts SET acknowledged_at=COALESCE(acknowledged_at,?) WHERE id=?", (now, receipt_id))
            row = connection.execute("SELECT * FROM agent_completion_receipts WHERE id=?", (receipt_id,)).fetchone()
        if not row:
            raise KeyError(receipt_id)
        return dict(row)

    def request_cancel(self, task_id: str, *, subtree: bool = True) -> list[str]:
        with self.database.transaction() as connection:
            if subtree:
                rows = connection.execute(
                    """WITH RECURSIVE descendants(id) AS (
                    SELECT id FROM agent_tasks WHERE id=?
                    UNION ALL SELECT child.id FROM agent_tasks child JOIN descendants d ON child.parent_task_id=d.id
                    ) SELECT id FROM descendants""", (task_id,)).fetchall()
            else:
                rows = connection.execute("SELECT id FROM agent_tasks WHERE id=?", (task_id,)).fetchall()
            ids = [row["id"] for row in rows]
            if ids:
                marks = ",".join("?" for _ in ids)
                connection.execute(f"UPDATE agent_tasks SET cancel_requested=1 WHERE id IN ({marks})", ids)
        for item in ids:
            self.append_event(item, "agent.cancel_requested", {})
        return ids

    def recover(self) -> int:
        now = utc_now()
        with self.database.transaction() as connection:
            rows = connection.execute("SELECT id,session_id,root_turn_id,execution_mode FROM agent_tasks WHERE status IN ('queued','running')").fetchall()
            cursor = connection.execute(
                "UPDATE agent_tasks SET status='interrupted',error='Backend restarted',finished_at=?,activity_phase='finished',stalled_at=NULL WHERE status IN ('queued','running')",
                (now,),
            )
            for row in rows:
                if row["execution_mode"] == "background":
                    connection.execute("INSERT OR IGNORE INTO agent_completion_receipts(id,task_id,session_id,root_turn_id,status,created_at) VALUES(?,?,?,?,?,?)",
                                       (str(uuid.uuid4()), row["id"], row["session_id"], row["root_turn_id"], "interrupted", now))
        return cursor.rowcount

    def get_command(self, command_id: str) -> dict[str, Any]:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM agent_task_commands WHERE id=?", (command_id,)).fetchone()
        if not row:
            raise KeyError(command_id)
        return self._decode_command(dict(row))

    @staticmethod
    def _decode_command(value: dict[str, Any]) -> dict[str, Any]:
        value["payload"] = json.loads(value.pop("payload_json"))
        return value

    def append_event(self, task_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.database.transaction() as connection:
            row = connection.execute("SELECT COALESCE(MAX(sequence),0)+1 n FROM agent_task_events WHERE task_id=?",
                                     (task_id,)).fetchone()
            sequence = int(row["n"])
            cursor = connection.execute(
                "INSERT INTO agent_task_events(task_id,sequence,type,payload_json,created_at) VALUES(?,?,?,?,?)",
                (task_id, sequence, event_type, json.dumps(payload, ensure_ascii=False), utc_now()),
            )
            result = connection.execute("SELECT * FROM agent_task_events WHERE id=?", (cursor.lastrowid,)).fetchone()
        value = dict(result)
        value["payload"] = json.loads(value.pop("payload_json"))
        return value

    def events(self, task_id: str, after: int = 0) -> list[dict[str, Any]]:
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_task_events WHERE task_id=? AND sequence>? ORDER BY sequence", (task_id, after)
            ).fetchall()
        result = []
        for row in rows:
            value = dict(row)
            value["payload"] = json.loads(value.pop("payload_json"))
            result.append(value)
        return result

    @staticmethod
    def _decode(value: dict[str, Any]) -> dict[str, Any]:
        value["context"] = json.loads(value.pop("context_json"))
        value["allowed_tools"] = json.loads(value.pop("allowed_tools_json"))
        value["output_schema"] = json.loads(value.pop("output_schema_json")) if value.get("output_schema_json") else None
        value.pop("output_schema_json", None)
        value["result"] = json.loads(value.pop("result_json")) if value.get("result_json") else None
        value.pop("result_json", None)
        value["cancel_requested"] = bool(value["cancel_requested"])
        value["activity"] = json.loads(value.pop("activity_json", "{}"))
        return value
