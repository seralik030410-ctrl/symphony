CREATE VIRTUAL TABLE messages_fts USING fts5(
    content,
    message_id UNINDEXED,
    session_id UNINDEXED,
    role UNINDEXED,
    tokenize='unicode61 remove_diacritics 2'
);

INSERT INTO messages_fts(content, message_id, session_id, role)
SELECT content, id, session_id, role
FROM messages
WHERE role IN ('user', 'assistant');

CREATE TRIGGER messages_fts_insert
AFTER INSERT ON messages
WHEN NEW.role IN ('user', 'assistant')
BEGIN
    INSERT INTO messages_fts(content, message_id, session_id, role)
    VALUES(NEW.content, NEW.id, NEW.session_id, NEW.role);
END;

CREATE TRIGGER messages_fts_update
AFTER UPDATE OF content, role, session_id ON messages
BEGIN
    DELETE FROM messages_fts WHERE message_id = OLD.id;
    INSERT INTO messages_fts(content, message_id, session_id, role)
    SELECT NEW.content, NEW.id, NEW.session_id, NEW.role
    WHERE NEW.role IN ('user', 'assistant');
END;

CREATE TRIGGER messages_fts_delete
AFTER DELETE ON messages
BEGIN
    DELETE FROM messages_fts WHERE message_id = OLD.id;
END;

CREATE TABLE agent_heartbeat_watches (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE REFERENCES agent_tasks(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    interval_seconds INTEGER NOT NULL DEFAULT 30 CHECK(interval_seconds BETWEEN 15 AND 3600),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'completed')),
    last_observed_status TEXT,
    last_observed_stalled INTEGER NOT NULL DEFAULT 0,
    next_check_at TEXT NOT NULL,
    last_checked_at TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX agent_heartbeat_watches_due
    ON agent_heartbeat_watches(status, next_check_at);
CREATE INDEX agent_heartbeat_watches_session
    ON agent_heartbeat_watches(session_id, status, created_at);

CREATE TABLE agent_heartbeat_events (
    id TEXT PRIMARY KEY,
    watch_id TEXT NOT NULL REFERENCES agent_heartbeat_watches(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    task_id TEXT NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK(type IN ('stalled', 'resumed', 'completed', 'failed', 'cancelled', 'interrupted')),
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    acknowledged_at TEXT,
    UNIQUE(watch_id, sequence)
);

CREATE INDEX agent_heartbeat_events_session
    ON agent_heartbeat_events(session_id, acknowledged_at, created_at);
