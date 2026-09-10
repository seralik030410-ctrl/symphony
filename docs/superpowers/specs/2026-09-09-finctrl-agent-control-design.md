# FinCtrl 3.0 — Agent Control and Durable Background Work

## Status

Approved direction for Stage 18. This design borrows bounded lifecycle ideas from the downloaded Hermes Agent source without importing Hermes or adopting its unsafe autonomy modes.

## Goal

Allow a person or the parent agent to inspect, steer, and stop active FinCtrl subagents while long-running delegated work continues durably in the background.

## Product contract

- Ordinary chat remains usable while background workers run.
- A subagent receives only its original context envelope plus explicitly addressed steering messages.
- Steering never changes permissions, tool allowlists, resource limits, provider credentials, or ownership.
- Stop is explicit, cascading only when `subtree=true`, and preserves the latest durable partial evidence.
- Lack of activity is visible as advisory health state; FinCtrl never auto-kills a slow 200B model merely for being quiet.
- Completion is persisted as a receipt attached to the originating turn. Refresh and restart cannot fabricate or lose a terminal result.
- Subagents never auto-approve dangerous actions, rewrite active memory/skills, or hand arbitrary host processes to a parent.

## Architecture

### Durable command mailbox

Migration `0023_agent_control.sql` adds `agent_task_commands`. Each command has an ordered per-task sequence, one of `steer` or `stop`, a bounded JSON payload, and `queued`, `delivered`, `applied`, or `rejected` lifecycle states. The store inserts commands transactionally and exposes compare-and-set delivery/application methods.

Steering is consumed by the executor at safe iteration boundaries. It is appended as a clearly labelled operator-guidance message and recorded in the task event stream. A completed task rejects new guidance. Stop uses the existing cancellation flag and task ownership tree; it does not wait for another model iteration.

### Activity and stall health

The migration adds `last_activity_at`, `activity_phase`, `activity_json`, and `stalled_at` to `agent_tasks`. Model, tool, queue, steering, and terminal transitions update these fields. Activity writes are throttled in the executor so streaming deltas do not create a database write per token.

The orchestrator owns a lightweight monitor. It marks a running task stalled after the profile's `stall_warning_seconds`, clears the marker when activity resumes, and emits one event per transition. Stalling is advisory. Deadline and explicit cancellation remain the only automatic termination mechanisms.

Profiles use generous warnings for large models: Conservative 300 seconds, Balanced 600 seconds, Maximum 1,800 seconds. Custom overrides cannot exceed the Maximum safety ceiling.

### Background delegation and receipts

`agent.delegate` accepts `background`. Foreground remains the default and returns consolidated results as before. Background mode creates and starts the same durable tasks but immediately returns task IDs and a receipt state of `running`.

Migration `0023_agent_control.sql` also adds `agent_completion_receipts`, unique per task. A terminal child writes exactly one receipt containing only task/result references and terminal metadata. The result itself remains canonical in `agent_tasks.result_json`. Receipt acknowledgement is a UI concern and never deletes the task.

The API exposes active/background tasks by session, command submission, command history, and receipt acknowledgement. The existing turn tree endpoint remains canonical for hierarchy.

### User interface

The existing inline subagent disclosure gains:

- explicit phase and last-activity text;
- a stalled warning that does not rely on colour;
- `Направить` and `Остановить` controls;
- a compact guidance composer with preserved input on failure;
- a background marker and durable completion notice.

The conversation remains primary. No new dashboard or modal is introduced. Controls use existing semantic theme tokens, visible labels, keyboard focus, 44-pixel targets, and reduced-motion behavior.

## API contract

- `POST /api/agents/tasks/{task_id}/commands` with `{type:"steer", message:string}` or `{type:"stop", subtree:boolean}`.
- `GET /api/agents/tasks/{task_id}/commands?after=<sequence>` returns durable command history.
- `GET /api/agents/sessions/{session_id}/background` returns non-acknowledged receipts and active background tasks.
- `POST /api/agents/receipts/{receipt_id}/acknowledge` marks a receipt seen.

All endpoints verify task/session ownership through canonical repository rows. Messages are UTF-8, stripped, and limited to 8,000 characters. Unknown, terminal, or cross-session targets fail closed.

## Failure and recovery

- A failed steering write leaves the UI text intact and presents an inline recovery action.
- Commands queued immediately before completion are rejected with a durable reason rather than silently discarded.
- Backend restart marks running tasks interrupted using the existing recovery rule and creates completion receipts for newly interrupted background tasks.
- A background task exception is consumed, persisted, and never becomes an unhandled event-loop exception.
- Receipt creation and terminal task transition are idempotent.

## Verification boundary

This is a code-first pass. Python syntax compilation, TypeScript type checking, migration numbering inspection, and diff validation may run. Pytest, Vitest, live-provider execution, production frontend build, and end-to-end acceptance remain deferred at the user's request.

## Explicit non-goals

- No subagent auto-approval or YOLO profile.
- No automatic memory or skill activation.
- No arbitrary process handoff.
- No remote messaging gateway, cron, MoA, or provider failover in Stage 18.
- No automatic cancellation solely because a task is marked stalled.
