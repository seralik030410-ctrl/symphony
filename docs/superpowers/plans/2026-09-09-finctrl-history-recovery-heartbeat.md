# FinCtrl History, Recovery and Heartbeat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe message search, validated SQLite recovery and non-executing background-agent heartbeat supervision.

**Architecture:** Three independent services share SQLite but no authority: FTS triggers index chat text, Database owns validated backups/restoration, and AgentHeartbeatService observes durable tasks plus refreshes active resource leases. APIs expose bounded redacted state and the UI shows only actionable events.

**Tech Stack:** Python 3.12, FastAPI, SQLite/FTS5, asyncio, React, TypeScript.

**Spec:** `docs/superpowers/specs/2026-09-09-finctrl-history-recovery-heartbeat-design.md`

## Global Constraints

- No behavioral tests, migration execution, live providers or production build in this code-first pass.
- Preserve corrupt database files before any automatic restore.
- Heartbeats never execute models, tools, commands, skills, network calls or new schedules.
- Search results are untrusted navigation data and never automatic prompt context.
- Keep at most five validated database backups.

---

### Task 1: Message FTS and repository search

**Files:**
- Create: `backend/storage/migrations/0025_history_heartbeat.sql`
- Create: `backend/agent/history_search.py`
- Modify: `backend/storage/repository.py`

**Interfaces:**
- Produces: `HistorySearch.search(query: str, limit: int) -> list[dict]`.

- [x] Create/backfill `messages_fts` and synchronization triggers for user/assistant rows.
- [x] Quote bounded lexical tokens and reject tokenless queries.
- [x] Join live sessions/messages and return plain bounded snippets.

### Task 2: Validated database backups and recovery

**Files:**
- Modify: `backend/storage/database.py`
- Modify: `backend/main.py`
- Modify: `backend/api/routes.py`

**Interfaces:**
- Produces: `Database.recovery_report`, `Database.quick_check(path)`, rolling `.backups` files.

- [x] Check primary integrity before migrations.
- [x] Back up through SQLite backup API and validate the result.
- [x] Preserve corrupt primary companions and restore only a validated backup.
- [x] Retain five backups and expose redacted recovery metadata in health.

### Task 3: Durable agent heartbeat watches

**Files:**
- Create: `backend/agent/heartbeat.py`
- Modify: `backend/agent/orchestrator.py`
- Modify: `backend/agent/executor.py`
- Modify: `backend/agent/task_store.py`
- Modify: `backend/main.py`

**Interfaces:**
- Produces: `AgentHeartbeatService.start()`, `shutdown()`, `ensure_watch(task_id)`, `acknowledge(event_id)`.

- [x] Persist one active watcher per background task and ordered meaningful events.
- [x] Observe due tasks without touching their activity timestamp.
- [x] Complete watchers at terminal state and recover active watchers after restart.
- [x] Refresh Resource Coordinator leases while agent execution owns them.

### Task 4: Search and heartbeat APIs

**Files:**
- Create: `backend/api/search.py`
- Modify: `backend/api/agents.py`
- Modify: `backend/main.py`

**Interfaces:**
- Produces: history search and heartbeat acknowledgement routes.

- [x] Register bounded query schemas and error translation.
- [x] Extend background state with watches/events.
- [x] Keep responses session-scoped and content-safe.

### Task 5: Compact UI surfaces

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/agents/AgentTaskTree.tsx`
- Modify: `frontend/src/agents/agents.css`

**Interfaces:**
- Consumes: history results and background heartbeat fields.

- [x] Add debounced chat-rail search with clear empty/error states.
- [x] Open a matched chat without mutating history.
- [x] Show and acknowledge only meaningful heartbeat alerts.
- [x] Preserve keyboard labels, 44px targets and mobile behavior.

### Task 6: Version and records

**Files:**
- Modify: `pyproject.toml`
- Modify: `backend/main.py`
- Modify: `backend/api/routes.py`
- Modify: `docs/superpowers/plans/2026-09-07-finctrl-3-multimodal-implementation.md`
- Modify: `IMPLEMENTATION_LOG.md`

**Interfaces:**
- Produces: version `0.20.0-dev` and accurate deferred-verification record.

- [x] Record boundaries, exclusions and implementation details.
- [x] Run Python compilation, TypeScript no-emit and whitespace validation only.
- [x] Leave behavioral acceptance explicitly deferred.
