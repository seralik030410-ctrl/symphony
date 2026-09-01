CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    provider TEXT NOT NULL CHECK (provider IN ('ollama', 'openai')),
    model TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    context_window INTEGER NOT NULL CHECK (context_window > 0),
    max_output INTEGER NOT NULL CHECK (max_output > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    turn_id TEXT,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('complete', 'streaming', 'cancelled', 'failed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    assistant_message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('queued', 'preparing', 'model_running', 'completed', 'failed', 'cancelled', 'interrupted')),
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    request_id TEXT NOT NULL,
    error TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (turn_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_messages_session_created
    ON messages(session_id, created_at, id);
CREATE INDEX IF NOT EXISTS idx_turns_session_created
    ON turns(session_id, created_at, id);
CREATE INDEX IF NOT EXISTS idx_events_turn_sequence
    ON events(turn_id, sequence);
CREATE INDEX IF NOT EXISTS idx_events_session_created
    ON events(session_id, created_at, id);

