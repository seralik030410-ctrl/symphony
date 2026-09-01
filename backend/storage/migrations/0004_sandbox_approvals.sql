ALTER TABLE sessions ADD COLUMN policy_profile TEXT NOT NULL DEFAULT 'restricted'
    CHECK (policy_profile IN ('strict', 'restricted', 'trusted'));

CREATE TABLE approvals (
    id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    tool_call_id TEXT NOT NULL REFERENCES tool_calls(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'denied', 'cancelled')),
    risk_level TEXT NOT NULL CHECK (risk_level IN ('low', 'medium', 'high')),
    reason TEXT NOT NULL,
    request_json TEXT NOT NULL,
    decision_note TEXT,
    requested_at TEXT NOT NULL,
    decided_at TEXT,
    UNIQUE(tool_call_id)
);

CREATE INDEX idx_approvals_turn_status ON approvals(turn_id, status);
CREATE INDEX idx_approvals_session_requested ON approvals(session_id, requested_at, id);
