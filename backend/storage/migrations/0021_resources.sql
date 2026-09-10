CREATE TABLE resource_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    profile TEXT NOT NULL CHECK (profile IN ('conservative','balanced','maximum','custom')),
    custom_limits_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE resource_groups (
    name TEXT PRIMARY KEY,
    capacity_units INTEGER NOT NULL CHECK (capacity_units > 0),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
    updated_at TEXT NOT NULL
);

CREATE TABLE resource_requests (
    id TEXT PRIMARY KEY,
    owner_type TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
    resource_class TEXT NOT NULL CHECK (resource_class IN ('realtime_voice','chat_vision','stt_tts','image','video')),
    priority INTEGER NOT NULL CHECK (priority BETWEEN 0 AND 4),
    claims_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL CHECK (status IN ('queued','paused','admitted','running','completed','failed','cancelled')),
    cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0,1)),
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    admitted_at TEXT,
    finished_at TEXT
);

CREATE INDEX idx_resource_requests_schedule
    ON resource_requests(status, priority, created_at, id);
CREATE INDEX idx_resource_requests_owner
    ON resource_requests(owner_type, owner_id, status);
CREATE INDEX idx_resource_requests_session
    ON resource_requests(session_id, created_at DESC);

CREATE TABLE resource_leases (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES resource_requests(id) ON DELETE CASCADE,
    resource_group TEXT NOT NULL,
    units INTEGER NOT NULL CHECK (units > 0),
    state TEXT NOT NULL CHECK (state IN ('active','released','expired')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    acquired_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    released_at TEXT,
    release_reason TEXT
);

CREATE INDEX idx_resource_leases_capacity
    ON resource_leases(resource_group, state, expires_at);
CREATE INDEX idx_resource_leases_request
    ON resource_leases(request_id, state);

CREATE TABLE resource_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL REFERENCES resource_requests(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(request_id, sequence)
);

CREATE TABLE resource_recovery_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT REFERENCES resource_requests(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
