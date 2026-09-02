from __future__ import annotations

import json
import uuid
from typing import Any

from backend.storage.database import Database, event_row_to_dict, row_to_dict, utc_now


ACTIVE_TURN_STATUSES = ("queued", "preparing", "model_running")
FINAL_TURN_STATUSES = ("completed", "failed", "cancelled", "interrupted")


class NotFoundError(LookupError):
    pass


class ConflictError(RuntimeError):
    pass


class Repository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_session(
        self,
        *,
        title: str,
        provider: str,
        model: str,
        system_prompt: str,
        context_window: int,
        max_output: int,
    ) -> dict[str, Any]:
        session_id = uuid.uuid4().hex
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO sessions(
                    id, title, provider, model, system_prompt,
                    context_window, max_output, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    title.strip(),
                    provider,
                    model,
                    system_prompt,
                    context_window,
                    max_output,
                    now,
                    now,
                ),
            )
        return self.get_session(session_id, include_history=True)

    def list_sessions(self) -> list[dict[str, Any]]:
        with self.database.read() as connection:
            rows = connection.execute(
                """
                SELECT
                    s.*,
                    COALESCE((
                        SELECT substr(m.content, 1, 90)
                        FROM messages m
                        WHERE m.session_id = s.id
                        ORDER BY m.created_at DESC, m.id DESC
                        LIMIT 1
                    ), '') AS last_message_preview,
                    EXISTS(
                        SELECT 1 FROM turns t
                        WHERE t.session_id = s.id
                          AND t.status IN ('queued', 'preparing', 'model_running')
                    ) AS active_turn
                FROM sessions s
                WHERE s.deleted_at IS NULL
                ORDER BY s.updated_at DESC, s.id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_session(self, session_id: str, *, include_history: bool) -> dict[str, Any]:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None or row["deleted_at"] is not None:
                raise NotFoundError("Session not found")
            result = dict(row)
            result["policy_profile"] = result.pop("permission_profile")
            if not include_history:
                return result
            result["messages"] = [
                self._message_from_row(item, connection)
                for item in connection.execute(
                    "SELECT * FROM messages WHERE session_id = ? ORDER BY sequence, id",
                    (session_id,),
                )
            ]
            result["turns"] = [
                self._turn_from_row(item, connection)
                for item in connection.execute(
                    "SELECT * FROM turns WHERE session_id = ? ORDER BY created_at, id",
                    (session_id,),
                )
            ]
            return result

    def update_session(self, session_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "title",
            "provider",
            "model",
            "system_prompt",
            "context_window",
            "max_output",
            "policy_profile",
        }
        updates = {key: value for key, value in changes.items() if key in allowed and value is not None}
        if "policy_profile" in updates:
            updates["permission_profile"] = updates.pop("policy_profile")
        if not updates:
            return self.get_session(session_id, include_history=True)
        updates["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with self.database.transaction() as connection:
            if set(updates) - {"title", "updated_at"}:
                active = connection.execute(
                    "SELECT 1 FROM turns WHERE session_id = ? "
                    "AND status IN ('queued', 'preparing', 'model_running') LIMIT 1",
                    (session_id,),
                ).fetchone()
                if active:
                    raise ConflictError("Stop the active turn before changing its settings or permissions")
            cursor = connection.execute(
                f"UPDATE sessions SET {assignments} WHERE id = ? AND deleted_at IS NULL",
                (*updates.values(), session_id),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("Session not found")
        return self.get_session(session_id, include_history=True)

    def trash_session(self, session_id: str) -> dict[str, Any]:
        with self.database.transaction() as connection:
            row = connection.execute("SELECT id, deleted_at FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                raise NotFoundError("Session not found")
            active = connection.execute(
                "SELECT 1 FROM turns WHERE session_id = ? AND status IN ('queued','preparing','model_running')",
                (session_id,),
            ).fetchone()
            if active:
                raise ConflictError("Stop the active turn before deleting this chat")
            connection.execute("UPDATE sessions SET deleted_at = COALESCE(deleted_at, ?) WHERE id = ?", (utc_now(), session_id))
        return {"id": session_id, "deleted": True, "recoverable": True}

    def restore_session(self, session_id: str) -> dict[str, Any]:
        with self.database.transaction() as connection:
            cursor = connection.execute("UPDATE sessions SET deleted_at = NULL, updated_at = ? WHERE id = ?", (utc_now(), session_id))
            if cursor.rowcount == 0:
                raise NotFoundError("Session not found")
        return self.get_session(session_id, include_history=True)

    def list_trashed_sessions(self) -> list[dict[str, Any]]:
        with self.database.read() as connection:
            return [dict(row) for row in connection.execute("SELECT id,title,deleted_at FROM sessions WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC")]

    @staticmethod
    def _purge_session_rows(connection: Any, session_id: str) -> None:
        """Delete one already-trashed session and every durable dependent row."""
        row = connection.execute(
            "SELECT deleted_at FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Session not found")
        if row["deleted_at"] is None:
            raise ConflictError("Move the chat to trash before deleting it permanently")

        # FTS5 is not connected by a foreign key, and several later-stage
        # tables intentionally predate cascade rules. Keep the deletion order
        # explicit so a permanent delete cannot leave searchable chat data.
        connection.execute("DELETE FROM file_chunks_fts WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM attachment_uses WHERE turn_id IN (SELECT id FROM turns WHERE session_id = ?)", (session_id,))
        connection.execute("DELETE FROM approvals WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM tool_calls WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM research_sources WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM artifact_versions WHERE artifact_id IN (SELECT id FROM artifacts WHERE session_id = ?)", (session_id,))
        connection.execute("DELETE FROM artifacts WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM file_chunks WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM indexed_files WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM attachments WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM memory_snapshots WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM research_settings WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def purge_session(self, session_id: str) -> dict[str, Any]:
        with self.database.transaction() as connection:
            self._purge_session_rows(connection, session_id)
        return {"id": session_id, "deleted": True, "recoverable": False}

    def purge_trashed_sessions(self) -> list[str]:
        with self.database.transaction() as connection:
            session_ids = [
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM sessions WHERE deleted_at IS NOT NULL ORDER BY deleted_at, id"
                )
            ]
            for session_id in session_ids:
                self._purge_session_rows(connection, session_id)
        return session_ids

    def create_turn(self, session_id: str, content: str, attachment_ids: list[str] | None = None, *, image_mode: str = "vision", retry_from_turn: str | None = None) -> dict[str, Any]:
        session = self.get_session(session_id, include_history=False)
        attachment_ids = attachment_ids or []
        if len(attachment_ids) > 8 or len(set(attachment_ids)) != len(attachment_ids):
            raise ConflictError("Attach at most eight distinct files")
        turn_id = uuid.uuid4().hex
        user_message_id = uuid.uuid4().hex
        assistant_message_id = uuid.uuid4().hex
        request_id = uuid.uuid4().hex
        now = utc_now()
        with self.database.transaction() as connection:
            active = connection.execute(
                """
                SELECT id FROM turns
                WHERE session_id = ? AND status IN ('queued', 'preparing', 'model_running')
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if active is not None:
                raise ConflictError("This session already has an active turn")
            first_sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO messages(
                    id, session_id, turn_id, role, content, status, created_at, updated_at, sequence
                ) VALUES (?, ?, ?, 'user', ?, 'complete', ?, ?, ?)
                """,
                (user_message_id, session_id, turn_id, content.strip(), now, now, first_sequence),
            )
            connection.execute(
                """
                INSERT INTO messages(
                    id, session_id, turn_id, role, content, status, created_at, updated_at, sequence
                ) VALUES (?, ?, ?, 'assistant', '', 'streaming', ?, ?, ?)
                """,
                (assistant_message_id, session_id, turn_id, now, now, first_sequence + 1),
            )
            connection.execute(
                """
                INSERT INTO turns(
                    id, session_id, user_message_id, assistant_message_id,
                    status, provider, model, request_id, created_at
                ) VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?)
                """,
                (
                    turn_id,
                    session_id,
                    user_message_id,
                    assistant_message_id,
                    session["provider"],
                    session["model"],
                    request_id,
                    now,
                ),
            )
            for attachment_id in attachment_ids:
                if retry_from_turn:
                    source = connection.execute("SELECT u.image_mode FROM attachment_uses u JOIN attachments a ON a.id=u.attachment_id WHERE u.turn_id=? AND a.id=? AND a.session_id=?", (retry_from_turn, attachment_id, session_id)).fetchone()
                    if source is None:
                        raise ConflictError("Retry attachment is not part of the original turn")
                    connection.execute("INSERT INTO attachment_uses(attachment_id,turn_id,message_id,image_mode) VALUES(?,?,?,?)", (attachment_id, turn_id, user_message_id, source["image_mode"]))
                    continue
                cursor = connection.execute(
                    "UPDATE attachments SET turn_id=?, message_id=? WHERE id=? AND session_id=? AND turn_id IS NULL",
                    (turn_id, user_message_id, attachment_id, session_id),
                )
                if cursor.rowcount != 1:
                    raise ConflictError("An attachment is missing, belongs to another chat, or was already sent")
                connection.execute("INSERT INTO attachment_uses(attachment_id,turn_id,message_id,image_mode) VALUES(?,?,?,?)", (attachment_id, turn_id, user_message_id, image_mode))
            message_count = connection.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user'",
                (session_id,),
            ).fetchone()[0]
            if message_count == 1 and session["title"] == "Новый чат":
                title = " ".join(content.strip().split())[:72] or "Новый чат"
                connection.execute(
                    "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                    (title, now, session_id),
                )
            else:
                connection.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
        return {
            "turn": self.get_turn(turn_id),
            "user_message": self.get_message(user_message_id),
            "assistant_message": self.get_message(assistant_message_id),
        }

    def get_turn(self, turn_id: str) -> dict[str, Any]:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM turns WHERE id = ?", (turn_id,)).fetchone()
            if row is None:
                raise NotFoundError("Turn not found")
            return self._turn_from_row(row, connection)

    def get_message(self, message_id: str) -> dict[str, Any]:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
            if row is None:
                raise NotFoundError("Message not found")
            return self._message_from_row(row, connection)

    def list_turn_attachments(self, turn_id: str) -> list[dict[str, Any]]:
        turn = self.get_turn(turn_id)
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT a.*,u.image_mode FROM attachments a JOIN attachment_uses u ON a.id=u.attachment_id WHERE u.turn_id=? AND a.session_id=? ORDER BY a.created_at,a.id",
                (turn_id, turn["session_id"]),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_context_messages(self, session_id: str) -> list[dict[str, Any]]:
        self.get_session(session_id, include_history=False)
        with self.database.read() as connection:
            rows = connection.execute(
                """
                SELECT role, content FROM messages
                WHERE session_id = ?
                  AND role IN ('user', 'assistant')
                  AND NOT (role = 'assistant' AND content = '')
                ORDER BY sequence, id
                """,
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_context_records(self, session_id: str) -> list[dict[str, Any]]:
        self.get_session(session_id, include_history=False)
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT id,role,content FROM messages WHERE session_id=? AND role IN ('user','assistant') "
                "AND NOT (role='assistant' AND content='') ORDER BY sequence,id",
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_turn_user_content(self, turn_id: str) -> str:
        turn = self.get_turn(turn_id)
        return self.get_message(turn["user_message_id"])["content"]

    def create_tool_call(
        self,
        *,
        turn_id: str,
        name: str,
        title: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        turn = self.get_turn(turn_id)
        call_id = uuid.uuid4().hex
        now = utc_now()
        with self.database.transaction() as connection:
            sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM tool_calls WHERE turn_id = ?",
                (turn_id,),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO tool_calls(
                    id, turn_id, session_id, sequence, name, title, arguments_json,
                    status, audit_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'requested', ?, ?)
                """,
                (
                    call_id,
                    turn_id,
                    turn["session_id"],
                    sequence,
                    name,
                    title,
                    json.dumps(arguments, ensure_ascii=False, separators=(",", ":")),
                    uuid.uuid4().hex,
                    now,
                ),
            )
        return self.get_tool_call(call_id)

    def get_tool_call(self, call_id: str) -> dict[str, Any]:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM tool_calls WHERE id = ?", (call_id,)).fetchone()
        if row is None:
            raise NotFoundError("Tool call not found")
        return self._tool_call_from_row(row)

    def list_tool_calls(self, turn_id: str) -> list[dict[str, Any]]:
        self.get_turn(turn_id)
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT * FROM tool_calls WHERE turn_id = ? ORDER BY sequence",
                (turn_id,),
            ).fetchall()
        return [self._tool_call_from_row(row) for row in rows]

    def set_tool_call_running(self, call_id: str) -> dict[str, Any]:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE tool_calls SET status = 'running', started_at = ? WHERE id = ?",
                (utc_now(), call_id),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("Tool call not found")
        return self.get_tool_call(call_id)

    def finish_tool_call(
        self,
        call_id: str,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        duration_ms: int | None = None,
    ) -> dict[str, Any]:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE tool_calls
                SET status = ?, result_json = ?, error_code = ?, error_message = ?,
                    duration_ms = ?, finished_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    json.dumps(result, ensure_ascii=False, separators=(",", ":"))
                    if result is not None
                    else None,
                    error_code,
                    error_message,
                    duration_ms,
                    utc_now(),
                    call_id,
                ),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("Tool call not found")
        return self.get_tool_call(call_id)

    def create_approval(
        self,
        *,
        turn_id: str,
        tool_call_id: str,
        risk_level: str,
        reason: str,
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        turn = self.get_turn(turn_id)
        approval_id = uuid.uuid4().hex
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO approvals(
                    id, turn_id, session_id, tool_call_id, status, risk_level,
                    reason, request_json, requested_at
                ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                """,
                (
                    approval_id,
                    turn_id,
                    turn["session_id"],
                    tool_call_id,
                    risk_level,
                    reason,
                    json.dumps(request_payload, ensure_ascii=False, separators=(",", ":")),
                    utc_now(),
                ),
            )
        return self.get_approval(approval_id)

    def get_approval(self, approval_id: str) -> dict[str, Any]:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if row is None:
            raise NotFoundError("Approval not found")
        value = dict(row)
        value["request"] = json.loads(value.pop("request_json"))
        return value

    def decide_approval(
        self,
        approval_id: str,
        *,
        approved: bool,
        note: str | None = None,
    ) -> dict[str, Any]:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE approvals
                SET status = ?, decision_note = ?, decided_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                ("approved" if approved else "denied", note, utc_now(), approval_id),
            )
            if cursor.rowcount == 0:
                existing = connection.execute(
                    "SELECT id FROM approvals WHERE id = ?",
                    (approval_id,),
                ).fetchone()
                if existing is None:
                    raise NotFoundError("Approval not found")
                raise ConflictError("Approval already has a decision")
        return self.get_approval(approval_id)

    def list_pending_approvals(self, session_id: str) -> list[dict[str, Any]]:
        self.get_session(session_id, include_history=False)
        with self.database.read() as connection:
            ids = [
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM approvals WHERE session_id = ? AND status = 'pending' ORDER BY requested_at",
                    (session_id,),
                )
            ]
        return [self.get_approval(approval_id) for approval_id in ids]

    def cancel_pending_approvals(self, turn_id: str, reason: str) -> int:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE approvals SET status = 'cancelled', decision_note = ?, decided_at = ?
                WHERE turn_id = ? AND status = 'pending'
                """,
                (reason, utc_now(), turn_id),
            )
        return cursor.rowcount

    def set_turn_status(
        self,
        turn_id: str,
        status: str,
        *,
        error: str | None = None,
        started: bool = False,
        finished: bool = False,
    ) -> dict[str, Any]:
        now = utc_now()
        columns = ["status = ?", "error = ?"]
        values: list[Any] = [status, error]
        if started:
            columns.append("started_at = COALESCE(started_at, ?)")
            values.append(now)
        if finished:
            columns.append("finished_at = ?")
            values.append(now)
        values.append(turn_id)
        with self.database.transaction() as connection:
            cursor = connection.execute(
                f"UPDATE turns SET {', '.join(columns)} WHERE id = ?",
                values,
            )
            if cursor.rowcount == 0:
                raise NotFoundError("Turn not found")
        return self.get_turn(turn_id)

    def request_cancel(self, turn_id: str) -> dict[str, Any]:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE turns SET cancel_requested = 1 WHERE id = ?",
                (turn_id,),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("Turn not found")
        return self.get_turn(turn_id)

    def append_assistant_delta(self, message_id: str, delta: str) -> None:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE messages
                SET content = content || ?, updated_at = ?
                WHERE id = ? AND role = 'assistant'
                """,
                (delta, utc_now(), message_id),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("Assistant message not found")

    def set_message_status(self, message_id: str, status: str) -> None:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE messages SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), message_id),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("Message not found")

    def append_event(self, turn_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        with self.database.transaction() as connection:
            turn = connection.execute(
                "SELECT session_id FROM turns WHERE id = ?",
                (turn_id,),
            ).fetchone()
            if turn is None:
                raise NotFoundError("Turn not found")
            sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM events WHERE turn_id = ?",
                (turn_id,),
            ).fetchone()[0]
            cursor = connection.execute(
                """
                INSERT INTO events(turn_id, session_id, sequence, type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    turn_id,
                    turn["session_id"],
                    sequence,
                    event_type,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
            event_id = cursor.lastrowid
            row = connection.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return event_row_to_dict(row)

    def list_events(self, turn_id: str, after_sequence: int = 0) -> list[dict[str, Any]]:
        self.get_turn(turn_id)
        with self.database.read() as connection:
            rows = connection.execute(
                """
                SELECT * FROM events
                WHERE turn_id = ? AND sequence > ?
                ORDER BY sequence
                """,
                (turn_id, after_sequence),
            ).fetchall()
        return [event_row_to_dict(row) for row in rows]

    def mark_inflight_interrupted(self) -> int:
        now = utc_now()
        with self.database.transaction() as connection:
            rows = connection.execute(
                """
                SELECT id, assistant_message_id FROM turns
                WHERE status IN ('queued', 'preparing', 'model_running')
                """
            ).fetchall()
            for row in rows:
                connection.execute(
                    """
                    UPDATE approvals SET status = 'cancelled', decision_note = ?, decided_at = ?
                    WHERE turn_id = ? AND status = 'pending'
                    """,
                    ("Backend restarted", now, row["id"]),
                )
                connection.execute(
                    """
                    UPDATE tool_calls
                    SET status = 'cancelled', error_code = 'backend_restart',
                        error_message = 'Backend restarted', finished_at = ?
                    WHERE turn_id = ? AND status IN ('requested', 'running')
                    """,
                    (now, row["id"]),
                )
                connection.execute(
                    "UPDATE turns SET status = 'interrupted', error = ?, finished_at = ? WHERE id = ?",
                    ("Backend restarted while the turn was active", now, row["id"]),
                )
                connection.execute(
                    "UPDATE messages SET status = 'failed', updated_at = ? WHERE id = ?",
                    (now, row["assistant_message_id"]),
                )
                sequence = connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM events WHERE turn_id = ?",
                    (row["id"],),
                ).fetchone()[0]
                session_id = connection.execute(
                    "SELECT session_id FROM turns WHERE id = ?",
                    (row["id"],),
                ).fetchone()[0]
                connection.execute(
                    """
                    INSERT INTO events(turn_id, session_id, sequence, type, payload_json, created_at)
                    VALUES (?, ?, ?, 'turn.interrupted', ?, ?)
                    """,
                    (
                        row["id"],
                        session_id,
                        sequence,
                        json.dumps({"reason": "backend_restart"}, separators=(",", ":")),
                        now,
                    ),
                )
        return len(rows)

    @staticmethod
    def _tool_call_from_row(row: Any) -> dict[str, Any]:
        value = dict(row)
        value["arguments"] = json.loads(value.pop("arguments_json"))
        raw_result = value.pop("result_json")
        value["result"] = json.loads(raw_result) if raw_result else None
        return value

    @staticmethod
    def _turn_from_row(row: Any, connection: Any) -> dict[str, Any]:
        value = dict(row)
        value["cancel_requested"] = bool(value["cancel_requested"])
        value["last_event_sequence"] = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) FROM events WHERE turn_id = ?",
            (value["id"],),
        ).fetchone()[0]
        return value

    @staticmethod
    def _message_from_row(row: Any, connection: Any) -> dict[str, Any]:
        value = dict(row)
        value["attachments"] = [
            dict(item)
            for item in connection.execute(
                "SELECT a.id,a.filename,a.mime_type,a.size,a.width,a.height,a.path,u.image_mode FROM attachments a JOIN attachment_uses u ON u.attachment_id=a.id WHERE u.message_id=? ORDER BY a.created_at,a.id",
                (value["id"],),
            )
        ]
        return value
