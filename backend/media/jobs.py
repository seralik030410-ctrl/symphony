from __future__ import annotations

import json
import uuid
from typing import Any

from backend.providers.secrets import SENSITIVE_KEY
from backend.storage.database import Database, utc_now
from backend.storage.repository import ConflictError, NotFoundError, Repository
from backend.tools.contracts import ToolError


FINAL_STATUSES = {"completed", "failed", "cancelled"}
ACTIVE_STATUSES = {"queued", "preparing", "running", "paused"}
TRANSITIONS = {
    "queued": {"preparing", "cancelled"},
    "preparing": {"running", "queued", "failed", "cancelled"},
    "running": {"paused", "completed", "failed", "cancelled"},
    "paused": {"queued", "running", "failed", "cancelled"},
}


def _validate_json(value: Any, *, depth: int = 0) -> None:
    if depth > 8:
        raise ToolError("invalid_job_input", "Media job input is too deeply nested")
    if isinstance(value, dict):
        if any(SENSITIVE_KEY.search(str(key)) for key in value):
            raise ToolError("invalid_job_input", "Media job input cannot contain secrets")
        for item in value.values():
            _validate_json(item, depth=depth + 1)
    elif isinstance(value, list):
        for item in value:
            _validate_json(item, depth=depth + 1)
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ToolError("invalid_job_input", "Media job input must contain JSON values only")


class MediaJobStore:
    def __init__(self, database: Database, repository: Repository) -> None:
        self.database = database
        self.repository = repository

    @staticmethod
    def _describe(row: Any) -> dict[str, Any]:
        value = dict(row)
        value["input"] = json.loads(value.pop("input_json"))
        value["cancel_requested"] = bool(value["cancel_requested"])
        return value

    def _event(self, connection: Any, job: Any, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        sequence = connection.execute(
            "SELECT COALESCE(MAX(sequence),0)+1 FROM media_job_events WHERE job_id=?", (job["id"],)
        ).fetchone()[0]
        now = utc_now()
        cursor = connection.execute(
            "INSERT INTO media_job_events(job_id,session_id,sequence,type,payload_json,created_at) VALUES(?,?,?,?,?,?)",
            (job["id"], job["session_id"], sequence, event_type,
             json.dumps(payload, ensure_ascii=False, separators=(",", ":")), now),
        )
        return {"id": cursor.lastrowid, "job_id": job["id"], "session_id": job["session_id"],
                "sequence": sequence, "type": event_type, "payload": payload, "created_at": now}

    def _turn_event(self, job: dict[str, Any], event_type: str, payload: dict[str, Any]) -> None:
        if job.get("turn_id"):
            self.repository.append_event(job["turn_id"], event_type, {"job_id": job["id"], "kind": job["kind"], **payload})

    def create(self, session_id: str, kind: str, input_value: dict[str, Any], *, turn_id: str | None = None,
               provider_profile_id: str | None = None, retry_of_job_id: str | None = None,
               attempt: int = 1) -> dict[str, Any]:
        _validate_json(input_value)
        encoded = json.dumps(input_value, ensure_ascii=False, separators=(",", ":"))
        maximum = 512_000 if kind.startswith("media.comfyui.") else 64_000
        if len(encoded.encode("utf-8")) > maximum:
            raise ToolError("invalid_job_input", f"Media job input exceeds {maximum // 1000} KB")
        job_id, now = uuid.uuid4().hex, utc_now()
        with self.database.transaction() as connection:
            if not connection.execute("SELECT 1 FROM sessions WHERE id=? AND deleted_at IS NULL", (session_id,)).fetchone():
                raise NotFoundError("Session not found")
            if turn_id:
                turn = connection.execute("SELECT session_id FROM turns WHERE id=?", (turn_id,)).fetchone()
                if not turn or turn["session_id"] != session_id:
                    raise NotFoundError("Turn not found in this chat")
            if provider_profile_id and not connection.execute(
                "SELECT 1 FROM provider_profiles WHERE id=? AND deleted_at IS NULL", (provider_profile_id,)
            ).fetchone():
                raise NotFoundError("Provider profile not found")
            connection.execute(
                """INSERT INTO media_jobs(id,session_id,turn_id,kind,status,input_json,provider_profile_id,
                   attempt,retry_of_job_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (job_id, session_id, turn_id, kind, "queued", encoded, provider_profile_id,
                 attempt, retry_of_job_id, now, now),
            )
            row = connection.execute("SELECT * FROM media_jobs WHERE id=?", (job_id,)).fetchone()
            self._event(connection, row, "media.job_queued", {"attempt": attempt})
        job = self._describe(row)
        self._turn_event(job, "media.job_queued", {"attempt": attempt})
        return job

    def get(self, session_id: str, job_id: str) -> dict[str, Any]:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM media_jobs WHERE id=? AND session_id=?", (job_id, session_id)).fetchone()
        if not row:
            raise NotFoundError("Media job not found in this chat")
        return self._describe(row)

    def list(self, session_id: str) -> list[dict[str, Any]]:
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT * FROM media_jobs WHERE session_id=? ORDER BY created_at DESC,id DESC", (session_id,)
            ).fetchall()
        return [self._describe(row) for row in rows]

    def events(self, session_id: str, job_id: str, after: int = 0) -> list[dict[str, Any]]:
        self.get(session_id, job_id)
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT * FROM media_job_events WHERE job_id=? AND session_id=? AND sequence>? ORDER BY sequence",
                (job_id, session_id, after),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            result.append(item)
        return result

    def claim_next(self) -> dict[str, Any] | None:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM media_jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1"
            ).fetchone()
            if not row:
                return None
            now = utc_now()
            cursor = connection.execute(
                "UPDATE media_jobs SET status='preparing',started_at=COALESCE(started_at,?),updated_at=? WHERE id=? AND status='queued'",
                (now, now, row["id"]),
            )
            if not cursor.rowcount:
                return None
            row = connection.execute("SELECT * FROM media_jobs WHERE id=?", (row["id"],)).fetchone()
            self._event(connection, row, "media.job_state_changed", {"status": "preparing"})
        return self._describe(row)

    def transition(self, session_id: str, job_id: str, status: str, *, progress: float | None = None,
                   result_asset_id: str | None = None, error_code: str | None = None,
                   error_message: str | None = None) -> dict[str, Any]:
        with self.database.transaction() as connection:
            row = connection.execute("SELECT * FROM media_jobs WHERE id=? AND session_id=?", (job_id, session_id)).fetchone()
            if not row:
                raise NotFoundError("Media job not found in this chat")
            current = row["status"]
            if current == status:
                return self._describe(row)
            if current in FINAL_STATUSES or status not in TRANSITIONS.get(current, set()):
                raise ConflictError(f"Media job cannot move from {current} to {status}")
            now = utc_now()
            next_progress = max(float(row["progress"]), min(1.0, progress if progress is not None else float(row["progress"])))
            if status == "completed":
                next_progress = 1.0
            connection.execute(
                """UPDATE media_jobs SET status=?,progress=?,result_asset_id=COALESCE(?,result_asset_id),
                   error_code=?,error_message=?,updated_at=?,finished_at=? WHERE id=?""",
                (status, next_progress, result_asset_id, error_code, error_message, now,
                 now if status in FINAL_STATUSES else None, job_id),
            )
            row = connection.execute("SELECT * FROM media_jobs WHERE id=?", (job_id,)).fetchone()
            payload = {"status": status, "progress": next_progress}
            if result_asset_id: payload["asset_id"] = result_asset_id
            if error_code: payload["error_code"] = error_code
            event_type = {
                "completed": "media.output_created", "failed": "media.job_failed",
                "cancelled": "media.job_cancelled",
            }.get(status, "media.job_state_changed")
            self._event(connection, row, event_type, payload)
        job = self._describe(row)
        self._turn_event(job, event_type, payload)
        return job

    def progress(self, session_id: str, job_id: str, value: float, message: str = "") -> dict[str, Any]:
        with self.database.transaction() as connection:
            row = connection.execute("SELECT * FROM media_jobs WHERE id=? AND session_id=?", (job_id, session_id)).fetchone()
            if not row:
                raise NotFoundError("Media job not found in this chat")
            if row["status"] not in {"preparing", "running"}:
                return self._describe(row)
            value = max(float(row["progress"]), min(0.99, max(0.0, value)))
            connection.execute("UPDATE media_jobs SET progress=?,updated_at=? WHERE id=?", (value, utc_now(), job_id))
            row = connection.execute("SELECT * FROM media_jobs WHERE id=?", (job_id,)).fetchone()
            payload = {"progress": value, "message": message[:200]}
            self._event(connection, row, "media.job_progress", payload)
        job = self._describe(row)
        self._turn_event(job, "media.job_progress", payload)
        return job

    def cancel(self, session_id: str, job_id: str) -> dict[str, Any]:
        job = self.get(session_id, job_id)
        if job["status"] in FINAL_STATUSES:
            return job
        with self.database.transaction() as connection:
            connection.execute("UPDATE media_jobs SET cancel_requested=1,updated_at=? WHERE id=?", (utc_now(), job_id))
        if job["status"] in {"queued", "paused"}:
            return self.transition(session_id, job_id, "cancelled")
        return self.get(session_id, job_id)

    def retry(self, session_id: str, job_id: str) -> dict[str, Any]:
        original = self.get(session_id, job_id)
        if original["status"] not in {"failed", "cancelled"}:
            raise ConflictError("Only failed or cancelled media jobs can be retried")
        return self.create(session_id, original["kind"], original["input"], turn_id=original["turn_id"],
                           provider_profile_id=original["provider_profile_id"], retry_of_job_id=job_id,
                           attempt=int(original["attempt"]) + 1)

    def recover(self) -> int:
        recovered: list[dict[str, Any]] = []
        with self.database.transaction() as connection:
            rows = connection.execute("SELECT * FROM media_jobs WHERE status IN ('preparing','running','paused')").fetchall()
            now = utc_now()
            for row in rows:
                status = "cancelled" if row["cancel_requested"] else "queued"
                connection.execute(
                    "UPDATE media_jobs SET status=?,progress=?,started_at=NULL,updated_at=?,finished_at=? WHERE id=?",
                    (status, row["progress"] if status == "cancelled" else 0, now,
                     now if status == "cancelled" else None, row["id"]),
                )
                self._event(connection, row, "media.job_state_changed", {"from": row["status"], "to": status, "recovered": True})
                recovered.append(self._describe(row))
        for job in recovered:
            self._turn_event(job, "media.job_state_changed", {"from": job["status"], "to": "cancelled" if job["cancel_requested"] else "queued", "recovered": True})
        return len(rows)
