CREATE TABLE IF NOT EXISTS skills (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    directory TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL CHECK (source_type IN ('bundled', 'zip', 'folder', 'git')),
    source_ref TEXT,
    mode TEXT NOT NULL DEFAULT 'auto' CHECK (mode IN ('off', 'explicit', 'auto', 'always')),
    priority INTEGER NOT NULL DEFAULT 50 CHECK (priority BETWEEN 0 AND 100),
    manifest_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_skills_active_slug
    ON skills(slug) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_skills_mode_priority
    ON skills(deleted_at, mode, priority DESC, name);
