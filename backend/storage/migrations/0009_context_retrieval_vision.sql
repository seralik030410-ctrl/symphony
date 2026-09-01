CREATE TABLE attachments (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    turn_id TEXT REFERENCES turns(id),
    message_id TEXT REFERENCES messages(id),
    path TEXT NOT NULL,
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size INTEGER NOT NULL CHECK(size >= 0),
    sha256 TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE(session_id, path)
);
CREATE INDEX attachments_session ON attachments(session_id, created_at);
CREATE INDEX attachments_turn ON attachments(turn_id);

CREATE TABLE indexed_files (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ready','failed')),
    error TEXT,
    characters INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(session_id, path)
);
CREATE INDEX indexed_files_session ON indexed_files(session_id, updated_at);

CREATE TABLE file_chunks (
    id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL REFERENCES indexed_files(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    path TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    start_char INTEGER NOT NULL,
    end_char INTEGER NOT NULL,
    token_estimate INTEGER NOT NULL,
    content TEXT NOT NULL,
    UNIQUE(file_id, ordinal)
);
CREATE INDEX file_chunks_session ON file_chunks(session_id, file_id, ordinal);
CREATE VIRTUAL TABLE file_chunks_fts USING fts5(
    content,
    chunk_id UNINDEXED,
    session_id UNINDEXED,
    path UNINDEXED,
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TABLE memory_snapshots (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    version INTEGER NOT NULL CHECK(version > 0),
    facts_json TEXT NOT NULL,
    decisions_json TEXT NOT NULL,
    open_tasks_json TEXT NOT NULL,
    artifact_index_json TEXT NOT NULL,
    source_message_ids_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(session_id, version)
);
CREATE INDEX memory_snapshots_session ON memory_snapshots(session_id, version DESC);
