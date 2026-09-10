CREATE TABLE provider_secret_refs (
    id TEXT PRIMARY KEY,
    storage_kind TEXT NOT NULL CHECK (storage_kind IN ('environment', 'desktop', 'memory')),
    locator TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(storage_kind, locator)
);

CREATE TABLE provider_profiles (
    id TEXT PRIMARY KEY,
    provider_type TEXT NOT NULL CHECK (provider_type IN ('ollama', 'openai_compatible')),
    title TEXT NOT NULL,
    base_url TEXT NOT NULL,
    default_model TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    is_local INTEGER NOT NULL DEFAULT 0 CHECK (is_local IN (0, 1)),
    secret_ref_id TEXT REFERENCES provider_secret_refs(id) ON DELETE SET NULL,
    request_timeout_seconds REAL NOT NULL DEFAULT 120 CHECK (request_timeout_seconds > 0),
    discovery_timeout_seconds REAL NOT NULL DEFAULT 2 CHECK (discovery_timeout_seconds > 0),
    config_json TEXT NOT NULL DEFAULT '{}',
    last_health_ok INTEGER CHECK (last_health_ok IN (0, 1)),
    last_health_message TEXT,
    last_checked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE provider_capability_overrides (
    profile_id TEXT NOT NULL REFERENCES provider_profiles(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    capability TEXT NOT NULL,
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    updated_at TEXT NOT NULL,
    PRIMARY KEY(profile_id, model, capability)
);

ALTER TABLE sessions ADD COLUMN provider_profile_id TEXT REFERENCES provider_profiles(id) ON DELETE SET NULL;
ALTER TABLE turns ADD COLUMN provider_profile_id TEXT REFERENCES provider_profiles(id) ON DELETE SET NULL;

CREATE INDEX idx_provider_profiles_enabled ON provider_profiles(enabled, provider_type, title);
CREATE INDEX idx_provider_capabilities_lookup ON provider_capability_overrides(profile_id, model, capability, enabled);

