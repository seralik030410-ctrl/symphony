ALTER TABLE sessions ADD COLUMN deleted_at TEXT;
CREATE INDEX sessions_visible_updated ON sessions(deleted_at, updated_at);
