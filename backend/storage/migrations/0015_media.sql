CREATE TABLE media_assets (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('image', 'video', 'audio')),
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size INTEGER NOT NULL CHECK (size > 0),
    sha256 TEXT NOT NULL,
    blob_path TEXT NOT NULL,
    preview_path TEXT,
    preview_mime_type TEXT,
    width INTEGER,
    height INTEGER,
    duration_seconds REAL,
    source TEXT NOT NULL,
    provider_profile_id TEXT REFERENCES provider_profiles(id) ON DELETE SET NULL,
    model TEXT,
    provenance_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE UNIQUE INDEX idx_media_assets_active_dedup
    ON media_assets(session_id, sha256, mime_type) WHERE deleted_at IS NULL;
CREATE INDEX idx_media_assets_gallery
    ON media_assets(session_id, deleted_at, created_at DESC);
CREATE INDEX idx_media_assets_blob
    ON media_assets(blob_path);

CREATE TABLE media_jobs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    turn_id TEXT REFERENCES turns(id) ON DELETE SET NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued','preparing','running','paused','completed','failed','cancelled')),
    input_json TEXT NOT NULL,
    result_asset_id TEXT REFERENCES media_assets(id) ON DELETE SET NULL,
    provider_profile_id TEXT REFERENCES provider_profiles(id) ON DELETE SET NULL,
    attempt INTEGER NOT NULL DEFAULT 1 CHECK (attempt > 0),
    retry_of_job_id TEXT REFERENCES media_jobs(id) ON DELETE SET NULL,
    progress REAL NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 1),
    cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1)),
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX idx_media_jobs_queue
    ON media_jobs(status, created_at, id);
CREATE INDEX idx_media_jobs_session
    ON media_jobs(session_id, created_at DESC);

CREATE TABLE media_job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES media_jobs(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(job_id, sequence)
);

CREATE INDEX idx_media_job_events_sequence
    ON media_job_events(job_id, sequence);

CREATE TABLE media_links (
    id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    turn_id TEXT REFERENCES turns(id) ON DELETE CASCADE,
    job_id TEXT REFERENCES media_jobs(id) ON DELETE CASCADE,
    relation TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_media_links_asset ON media_links(asset_id, relation);
CREATE INDEX idx_media_links_scope ON media_links(session_id, turn_id, job_id);

