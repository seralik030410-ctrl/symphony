-- Keep the old CHECK-constrained column for backwards-compatible database history.
-- The application now reads/writes permission_profile, exposed as policy_profile in the API.
ALTER TABLE sessions ADD COLUMN permission_profile TEXT NOT NULL DEFAULT 'build'
    CHECK (permission_profile IN ('read_only', 'project_edit', 'build', 'full_manual'));
UPDATE sessions SET permission_profile = CASE policy_profile
    WHEN 'strict' THEN 'read_only'
    WHEN 'trusted' THEN 'full_manual'
    ELSE 'build' END;
