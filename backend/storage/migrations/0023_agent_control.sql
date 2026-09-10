ALTER TABLE agent_tasks ADD COLUMN execution_mode TEXT NOT NULL DEFAULT 'foreground'
    CHECK(execution_mode IN ('foreground','background'));
ALTER TABLE agent_tasks ADD COLUMN last_activity_at TEXT;
ALTER TABLE agent_tasks ADD COLUMN activity_phase TEXT NOT NULL DEFAULT 'queued';
ALTER TABLE agent_tasks ADD COLUMN activity_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE agent_tasks ADD COLUMN stalled_at TEXT;

CREATE TABLE agent_task_commands (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('steer','stop')),
    payload_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','delivered','applied','rejected')),
    rejection_reason TEXT,
    created_at TEXT NOT NULL,
    delivered_at TEXT,
    applied_at TEXT,
    UNIQUE(task_id, sequence)
);

CREATE INDEX idx_agent_task_commands_pending
    ON agent_task_commands(task_id, status, sequence);

CREATE TABLE agent_completion_receipts (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE REFERENCES agent_tasks(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    root_turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK(status IN ('completed','failed','cancelled','interrupted')),
    created_at TEXT NOT NULL,
    acknowledged_at TEXT
);

CREATE INDEX idx_agent_completion_receipts_session
    ON agent_completion_receipts(session_id, acknowledged_at, created_at);
