from __future__ import annotations

import hashlib
import json
import uuid

from backend.research.network import domain
from backend.storage.database import utc_now


class ResearchStore:
    def __init__(self, database):
        self.database = database

    def settings(self, session_id):
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM research_settings WHERE session_id=?", (session_id,)).fetchone()
        return {"enabled": bool(row["enabled"]) if row else False,
                "allowed_domains": json.loads(row["allowed_domains_json"]) if row else [],
                "search_provider": "DuckDuckGo Lite", "search_domain": "lite.duckduckgo.com"}

    def update(self, session_id, *, enabled, allowed_domains):
        domains = sorted({domain(item) for item in allowed_domains})
        if len(domains) > 50:
            raise ValueError("В allowlist может быть не больше 50 доменов")
        with self.database.transaction() as connection:
            connection.execute("INSERT INTO research_settings(session_id,enabled,allowed_domains_json,updated_at) VALUES(?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET enabled=excluded.enabled,allowed_domains_json=excluded.allowed_domains_json,updated_at=excluded.updated_at",
                               (session_id, int(enabled), json.dumps(domains), utc_now()))
        return self.settings(session_id)

    def save_source(self, session_id, turn_id, *, url, title, content, kind, published_at=None):
        value = {"id": uuid.uuid4().hex, "session_id": session_id, "turn_id": turn_id,
                 "url": url, "title": title[:240], "content": content[:20_000], "kind": kind,
                 "published_at": published_at, "checked_at": utc_now(),
                 "sha256": hashlib.sha256(content[:20_000].encode()).hexdigest()}
        with self.database.transaction() as connection:
            # A tool cannot forge provenance into a turn owned by another session.
            owner = connection.execute("SELECT session_id FROM turns WHERE id=?", (turn_id,)).fetchone()
            if owner is None or owner[0] != session_id:
                raise ValueError("Source turn does not belong to this session")
            connection.execute("INSERT INTO research_sources(id,session_id,turn_id,url,title,kind,published_at,checked_at,content,sha256) VALUES(:id,:session_id,:turn_id,:url,:title,:kind,:published_at,:checked_at,:content,:sha256)", value)
        return self.public_source(value)

    def sources(self, session_id, turn_id=None):
        with self.database.read() as connection:
            rows = connection.execute("SELECT * FROM research_sources WHERE session_id=? AND (? IS NULL OR turn_id=?) ORDER BY checked_at DESC LIMIT 100", (session_id, turn_id, turn_id)).fetchall()
        return [self.public_source(dict(row)) for row in rows]

    @staticmethod
    def public_source(value):
        return {**{key: val for key, val in value.items() if key != "content"}, "excerpt": value["content"][:500], "trust": "untrusted"}
