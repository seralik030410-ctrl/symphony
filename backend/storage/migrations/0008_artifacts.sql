CREATE TABLE artifacts (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    format TEXT NOT NULL CHECK (format IN ('pdf','xlsx','docx','pptx')),
    created_at TEXT NOT NULL
);
CREATE INDEX artifacts_session ON artifacts(session_id);
CREATE TABLE artifact_versions (
    artifact_id TEXT NOT NULL REFERENCES artifacts(id),
    version INTEGER NOT NULL CHECK (version > 0),
    turn_id TEXT NOT NULL REFERENCES turns(id),
    title TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(artifact_id, version)
);
