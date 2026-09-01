CREATE TABLE research_settings (
    session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
    allowed_domains_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL
);
CREATE TABLE research_sources (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('search_result','page')),
    published_at TEXT,
    checked_at TEXT NOT NULL,
    content TEXT NOT NULL,
    sha256 TEXT NOT NULL
);
CREATE INDEX research_sources_turn ON research_sources(session_id,turn_id);
