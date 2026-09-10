ALTER TABLE agent_settings ADD COLUMN lazy_tools_enabled INTEGER NOT NULL DEFAULT 1;
ALTER TABLE agent_settings ADD COLUMN role_routes_json TEXT NOT NULL DEFAULT '{}';

ALTER TABLE agent_tasks ADD COLUMN role TEXT NOT NULL DEFAULT 'worker'
    CHECK(role IN ('worker','orchestrator','code','research','vision','media','review'));
