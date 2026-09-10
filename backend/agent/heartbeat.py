from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.agent.task_store import AgentTaskStore
from backend.storage.database import Database, utc_now


TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


class AgentHeartbeatService:
    """Observes durable background task state without executing any work."""

    def __init__(self, database: Database, tasks: AgentTaskStore) -> None:
        self.database = database
        self.tasks = tasks
        self._monitor_task: asyncio.Task[None] | None = None

    def ensure_watch(self, task_id: str, *, interval_seconds: int = 30) -> dict[str, Any]:
        task = self.tasks.get(task_id)
        if task["execution_mode"] != "background":
            raise ValueError("Heartbeat watches are only available for background tasks")
        interval = max(15, min(int(interval_seconds), 3600))
        now = utc_now()
        watch_id = str(uuid.uuid4())
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO agent_heartbeat_watches(
                       id,task_id,session_id,interval_seconds,status,last_observed_status,
                       last_observed_stalled,next_check_at,created_at
                   ) VALUES(?,?,?,?,'active',?,0,?,?)""",
                (watch_id, task_id, task["session_id"], interval, task["status"], now, now),
            )
            row = connection.execute(
                "SELECT * FROM agent_heartbeat_watches WHERE task_id=?", (task_id,)
            ).fetchone()
        return self._decode_watch(dict(row))

    def start(self) -> None:
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._monitor(), name="agent-heartbeat-monitor")

    def reconcile_after_restart(self) -> int:
        """Observe every persisted active watch immediately after task recovery."""
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT id FROM agent_heartbeat_watches WHERE status='active' ORDER BY created_at"
            ).fetchall()
        for row in rows:
            self._observe(str(row["id"]))
        return len(rows)

    async def shutdown(self) -> None:
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            await asyncio.gather(self._monitor_task, return_exceptions=True)
            self._monitor_task = None

    async def _monitor(self) -> None:
        while True:
            try:
                self.run_due()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Observation failures are retried; they must never affect task execution.
                pass
            await asyncio.sleep(15)

    def run_due(self) -> int:
        now = utc_now()
        with self.database.read() as connection:
            rows = connection.execute(
                """SELECT watch.*, task.status AS task_status, task.stalled_at,
                          task.activity_phase, task.finished_at
                   FROM agent_heartbeat_watches watch
                   JOIN agent_tasks task ON task.id=watch.task_id
                   WHERE watch.status='active' AND watch.next_check_at<=?
                   ORDER BY watch.next_check_at LIMIT 100""",
                (now,),
            ).fetchall()
        for row in rows:
            self._observe(str(row["id"]))
        return len(rows)

    def _observe(self, watch_id: str) -> None:
        with self.database.transaction() as connection:
            # BEGIN IMMEDIATE serializes observers. Re-reading here makes the
            # state comparison and event insertion one atomic transition.
            row = connection.execute(
                """SELECT watch.*, task.status AS task_status, task.stalled_at,
                          task.activity_phase
                   FROM agent_heartbeat_watches watch
                   JOIN agent_tasks task ON task.id=watch.task_id
                   WHERE watch.id=? AND watch.status='active'""",
                (watch_id,),
            ).fetchone()
            if row is None:
                return
            watch = dict(row)
            task_status = str(watch["task_status"])
            stalled = bool(watch["stalled_at"])
            previous_stalled = bool(watch["last_observed_stalled"])
            event_type: str | None = None
            if task_status in TERMINAL and watch["last_observed_status"] not in TERMINAL:
                event_type = task_status
            elif stalled and not previous_stalled:
                event_type = "stalled"
            elif not stalled and previous_stalled and task_status == "running":
                event_type = "resumed"

            now = utc_now()
            next_check = (datetime.now(UTC) + timedelta(
                seconds=int(watch["interval_seconds"])
            )).isoformat(timespec="milliseconds")
            if event_type:
                sequence = connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM agent_heartbeat_events WHERE watch_id=?",
                    (watch["id"],),
                ).fetchone()[0]
                connection.execute(
                    """INSERT INTO agent_heartbeat_events(
                           id,watch_id,sequence,task_id,session_id,type,payload_json,created_at
                       ) VALUES(?,?,?,?,?,?,?,?)""",
                    (str(uuid.uuid4()), watch["id"], sequence, watch["task_id"], watch["session_id"],
                     event_type, json.dumps({"activity_phase": watch["activity_phase"]}, ensure_ascii=False), now),
                )
            terminal = task_status in TERMINAL
            connection.execute(
                """UPDATE agent_heartbeat_watches
                   SET status=?,last_observed_status=?,last_observed_stalled=?,
                       last_checked_at=?,next_check_at=?,completed_at=?
                   WHERE id=? AND status='active'""",
                ("completed" if terminal else "active", task_status, int(stalled), now,
                 next_check, now if terminal else None, watch["id"]),
            )

    def for_session(self, session_id: str) -> dict[str, list[dict[str, Any]]]:
        with self.database.read() as connection:
            watches = connection.execute(
                """SELECT watch.*, task.goal, task.activity_phase, task.stalled_at,
                          task.status AS task_status
                   FROM agent_heartbeat_watches watch
                   JOIN agent_tasks task ON task.id=watch.task_id
                   WHERE watch.session_id=? AND watch.status='active'
                   ORDER BY watch.created_at""",
                (session_id,),
            ).fetchall()
            events = connection.execute(
                """SELECT event.*, task.goal
                   FROM agent_heartbeat_events event
                   JOIN agent_tasks task ON task.id=event.task_id
                   WHERE event.session_id=? AND event.acknowledged_at IS NULL
                   ORDER BY event.created_at, event.watch_id, event.sequence""",
                (session_id,),
            ).fetchall()
        return {
            "watches": [self._decode_watch(dict(row)) for row in watches],
            "events": [self._decode_event(dict(row)) for row in events],
        }

    def acknowledge(self, event_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE agent_heartbeat_events SET acknowledged_at=COALESCE(acknowledged_at,?) WHERE id=?",
                (now, event_id),
            )
            row = connection.execute("SELECT * FROM agent_heartbeat_events WHERE id=?", (event_id,)).fetchone()
        if not row:
            raise KeyError(event_id)
        return self._decode_event(dict(row))

    @staticmethod
    def _decode_watch(value: dict[str, Any]) -> dict[str, Any]:
        value["last_observed_stalled"] = bool(value["last_observed_stalled"])
        return value

    @staticmethod
    def _decode_event(value: dict[str, Any]) -> dict[str, Any]:
        value["payload"] = json.loads(value.pop("payload_json"))
        return value
