CREATE TABLE agent_tasks (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    root_turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    parent_task_id TEXT REFERENCES agent_tasks(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL DEFAULT 0,
    depth INTEGER NOT NULL DEFAULT 0 CHECK(depth >= 0),
    goal TEXT NOT NULL,
    context_json TEXT NOT NULL DEFAULT '{}',
    provider_profile_id TEXT,
    model TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed','cancelled','interrupted')),
    permission_profile TEXT NOT NULL,
    allowed_tools_json TEXT NOT NULL DEFAULT '[]',
    output_schema_json TEXT,
    result_json TEXT,
    error TEXT,
    max_steps INTEGER NOT NULL,
    max_tool_calls INTEGER NOT NULL,
    max_input_tokens INTEGER NOT NULL,
    max_output_tokens INTEGER NOT NULL,
    deadline_seconds INTEGER NOT NULL,
    used_steps INTEGER NOT NULL DEFAULT 0,
    used_tool_calls INTEGER NOT NULL DEFAULT 0,
    used_input_tokens INTEGER NOT NULL DEFAULT 0,
    used_output_tokens INTEGER NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX idx_agent_tasks_root ON agent_tasks(root_turn_id, parent_task_id, ordinal);
CREATE INDEX idx_agent_tasks_session ON agent_tasks(session_id, created_at);
CREATE INDEX idx_agent_tasks_status ON agent_tasks(status, created_at);

CREATE TABLE agent_task_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(task_id, sequence)
);

CREATE INDEX idx_agent_task_events_task ON agent_task_events(task_id, sequence);

CREATE TABLE agent_settings (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    enabled INTEGER NOT NULL DEFAULT 1,
    profile TEXT NOT NULL DEFAULT 'balanced',
    overrides_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE agent_learning_proposals (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    task_id TEXT REFERENCES agent_tasks(id) ON DELETE SET NULL,
    kind TEXT NOT NULL CHECK(kind IN ('memory','skill')),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
    created_at TEXT NOT NULL,
    decided_at TEXT
);

CREATE INDEX idx_agent_learning_pending ON agent_learning_proposals(status, created_at);
