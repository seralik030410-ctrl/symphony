# FinCtrl 3.0 Stage 20 — History Search, Database Recovery and Heartbeats

## Goal

Make long-lived FinCtrl installations searchable and recoverable, while supervising background agents without importing Hermes process handoff or unrestricted cron behavior.

## History search

SQLite FTS5 indexes only `user` and `assistant` message text. Insert, update and delete triggers keep the index synchronized, including streamed assistant deltas, and the migration backfills existing messages. Results exclude trashed chats, remain session-aware, return bounded plain-text snippets and never become trusted instructions or automatic model context.

The API accepts a non-empty query up to 300 characters and a limit of 1–50. Search terms are converted to quoted FTS tokens instead of accepting raw FTS syntax. The chat rail exposes a compact search field; selecting a result opens its chat. Search is navigation, not memory mutation.

## Database safety and recovery

Before migrations, Database performs `PRAGMA quick_check`. A healthy database with pending migrations is backed up through SQLite's online backup API. After successful initialization, a validated rolling backup is created; at most five healthy backups are retained.

If the primary database is corrupt, FinCtrl scans newest backups, validates each with `quick_check`, preserves the damaged primary plus WAL/SHM companions under a timestamped recovery name, and restores the newest valid backup. If none is valid, startup stops with an actionable error and leaves all files untouched. Recovery never fabricates rows or silently drops individual records. Runtime health reports whether recovery occurred and which backup was used without exposing user content.

## Agent heartbeat supervision

Every background agent task receives a durable watcher. A scheduler observes it at a bounded interval (15–3600 seconds), writes events only when the state meaningfully changes (`stalled`, `resumed`, or a terminal status), and completes the watcher when the task ends. It never invokes a model, command, tool, skill, network request, or another watcher.

While an agent owns a Resource Coordinator lease, an in-process heartbeat refreshes that lease at a safe interval. Heartbeat observations do not update `agent_tasks.last_activity_at`, so they cannot hide a genuinely stalled model/tool call. Watch events and completion remain visible after refresh and can be acknowledged independently.

## API and UI

- `GET /api/search/history?q=&limit=` returns bounded chat/message matches.
- `GET /api/agents/sessions/{session_id}/background` also returns active watches and unacknowledged heartbeat events.
- `POST /api/agents/heartbeat-events/{event_id}/acknowledge` acknowledges one notification.
- The task tree displays meaningful heartbeat alerts; routine checks remain silent.
- `/api/health` includes redacted database recovery metadata.

## Exclusions

No general cron expressions, arbitrary prompts, autonomous follow-up turns, model spawning, process handoff, remote SSH backends, auto-approval, automatic memory/skill activation, or fail-open recovery are introduced.

## Deferred acceptance

The later test phase must verify FTS trigger parity, query escaping, trash isolation, backup validation and retention, corrupt-primary restore, no-backup failure, watcher transition deduplication, lease survival, restart recovery, UI navigation and full regressions. Stage 20 is not accepted until those checks run.
