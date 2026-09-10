from __future__ import annotations

import json
import uuid
from typing import Any

from backend.storage.database import Database, utc_now


class LearningProposalStore:
    """Staging area: proposals never alter active memory or skills automatically."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def propose(self, *, session_id: str, task_id: str | None, kind: str,
                title: str, content: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
        proposal_id = str(uuid.uuid4())
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO agent_learning_proposals(id,session_id,task_id,kind,title,content,evidence_json,status,created_at) VALUES(?,?,?,?,?,?,?,'pending',?)",
                (proposal_id, session_id, task_id, kind, title, content,
                 json.dumps(evidence, ensure_ascii=False), utc_now()),
            )
        return self.get(proposal_id)

    def get(self, proposal_id: str) -> dict[str, Any]:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM agent_learning_proposals WHERE id=?", (proposal_id,)).fetchone()
        if not row:
            raise KeyError(proposal_id)
        value = dict(row)
        value["evidence"] = json.loads(value.pop("evidence_json"))
        return value

    def list(self, *, session_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        where, params = [], []
        if session_id:
            where.append("session_id=?"); params.append(session_id)
        if status:
            where.append("status=?"); params.append(status)
        sql = "SELECT * FROM agent_learning_proposals" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY created_at DESC"
        with self.database.read() as connection:
            rows = connection.execute(sql, params).fetchall()
        result = []
        for row in rows:
            value = dict(row); value["evidence"] = json.loads(value.pop("evidence_json")); result.append(value)
        return result

    def decide(self, proposal_id: str, approved: bool) -> dict[str, Any]:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE agent_learning_proposals SET status=?,decided_at=? WHERE id=? AND status='pending'",
                ("approved" if approved else "rejected", utc_now(), proposal_id),
            )
        if cursor.rowcount != 1:
            raise ValueError("Proposal is missing or already decided")
        return self.get(proposal_id)
