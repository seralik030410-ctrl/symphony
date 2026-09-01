CREATE TABLE IF NOT EXISTS tool_calls (
    id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    name TEXT NOT NULL,
    title TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('requested', 'running', 'completed', 'failed', 'cancelled')),
    result_json TEXT,
    error_code TEXT,
    error_message TEXT,
    duration_ms INTEGER,
    audit_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    UNIQUE(turn_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_turn_sequence
    ON tool_calls(turn_id, sequence);
CREATE INDEX IF NOT EXISTS idx_tool_calls_session_created
    ON tool_calls(session_id, created_at, id);

