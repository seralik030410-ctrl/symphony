from __future__ import annotations

import re
from typing import Any

from backend.storage.database import Database


TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)


class HistorySearch:
    """Bounded lexical message search used only for user-driven navigation."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        clean = query.strip()
        if not clean or len(clean) > 300:
            raise ValueError("Search query must contain 1-300 visible characters")
        tokens = TOKEN_PATTERN.findall(clean)[:16]
        if not tokens:
            raise ValueError("Search query must contain at least one letter or number")
        expression = " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)
        bounded_limit = max(1, min(int(limit), 50))
        with self.database.read() as connection:
            rows = connection.execute(
                """SELECT messages.id AS message_id,
                          messages.session_id,
                          messages.turn_id,
                          messages.role,
                          sessions.title AS session_title,
                          snippet(messages_fts, 0, '', '', '…', 24) AS snippet,
                          messages.created_at,
                          bm25(messages_fts) AS rank
                   FROM messages_fts
                   JOIN messages ON messages.id = messages_fts.message_id
                   JOIN sessions ON sessions.id = messages.session_id
                   WHERE messages_fts MATCH ?
                     AND messages.role IN ('user', 'assistant')
                     AND sessions.deleted_at IS NULL
                   ORDER BY rank, messages.created_at DESC
                   LIMIT ?""",
                (expression, bounded_limit),
            ).fetchall()
        results = []
        for row in rows:
            value = dict(row)
            value["snippet"] = str(value.get("snippet") or "")[:500]
            results.append(value)
        return results
