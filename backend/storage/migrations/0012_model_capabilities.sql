CREATE TABLE model_capability_overrides (
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    overrides_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(provider, model)
);
