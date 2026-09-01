ALTER TABLE memory_snapshots ADD COLUMN kind TEXT NOT NULL DEFAULT 'manual';
ALTER TABLE memory_snapshots ADD COLUMN model TEXT;
ALTER TABLE memory_snapshots ADD COLUMN input_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE memory_snapshots ADD COLUMN output_tokens INTEGER NOT NULL DEFAULT 0;
