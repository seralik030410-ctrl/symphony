# FinCtrl Agent Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add steerable, stoppable, observable and durable background subagent execution to FinCtrl.

**Architecture:** Extend the existing Stage 17 task/event model with a durable command mailbox, advisory activity health and idempotent completion receipts. Keep foreground delegation compatible while allowing background dispatch to return immediately; surface controls inside the existing inline task tree.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, asyncio, Pydantic, React 19, TypeScript, vanilla CSS.

**Spec:** `docs/superpowers/specs/2026-09-09-finctrl-agent-control-design.md`

## Global Constraints

- Continue in the user's existing working `main` workspace because Stages 9–17 are uncommitted dependencies explicitly authorized for in-place development.
- Do not run pytest, Vitest, live providers, a production frontend build, Rust/Cargo, or end-to-end tests in this code-first pass.
- Steering is limited to 8,000 UTF-8 characters and cannot alter permissions, tools, limits, credentials, provider, or ownership.
- Stalling is advisory; only deadline or explicit cancellation terminates work.
- Conservative/Balanced/Maximum stall warnings are exactly 300/600/1,800 seconds.
- No auto-approval, active memory/skill mutation, arbitrary process handoff, remote gateway, cron, MoA, or provider failover.

---

### Task 1: Durable mailbox, activity health, and receipts

**Files:**
- Create: `backend/storage/migrations/0023_agent_control.sql`
- Modify: `backend/agent/contracts.py`
- Modify: `backend/agent/task_store.py`

**Interfaces:**
- Produces `AgentCommandType`, `AgentExecutionMode`, and `AgentLimits.stall_warning_seconds`.
- Produces store methods `queue_command`, `commands`, `claim_steering`, `apply_command`, `reject_command`, `touch_activity`, `mark_stalled`, `clear_stalled`, `background_for_session`, and `acknowledge_receipt`.

- [ ] Add migration columns for execution mode/activity health plus command and receipt tables with unique ordering/idempotency indexes.
- [ ] Extend all three agent profiles with exact stall-warning values and preserve the Maximum override ceiling.
- [ ] Implement bounded transactional command insertion and compare-and-set lifecycle updates.
- [ ] Implement throttling-ready activity updates and one-transition stalled markers.
- [ ] Make terminal writes idempotent and create exactly one receipt for background tasks.
- [ ] Extend restart recovery to create receipts for interrupted background work.
- [ ] Run Python bytecode compilation and `git diff --check`; do not run behavioral tests.

### Task 2: Steerable executor and background orchestration

**Files:**
- Modify: `backend/agent/executor.py`
- Modify: `backend/agent/orchestrator.py`
- Modify: `backend/tools/delegation.py`

**Interfaces:**
- Consumes Task 1 command/activity/receipt store methods.
- Produces `AgentOrchestrator.command(task_id, command_type, payload)` and background-aware `delegate(..., background=False)`.

- [ ] Update activity at queue, resource wait, model, tool, steering and terminal boundaries, throttling streaming updates to at most one durable write per 10 seconds.
- [ ] Consume queued steering before every model iteration and append labelled operator guidance without mutating the original context.
- [ ] Add `background` to delegation input; return IDs immediately when true and preserve current foreground result ordering.
- [ ] Ensure every background task consumes exceptions and persists terminal state/receipt.
- [ ] Add `agent.control` for list/steer/stop with immutable permission scope and no new privileged capability.
- [ ] Add an orchestrator monitor that marks/clears advisory stall state and shuts down cleanly.
- [ ] Run Python bytecode compilation and `git diff --check`; do not run behavioral tests.

### Task 3: API controls and durable completion reads

**Files:**
- Modify: `backend/api/agents.py`
- Modify: `backend/main.py`

**Interfaces:**
- Consumes `AgentOrchestrator.command` and Task 1 store methods.
- Produces the four HTTP contracts named in the spec.

- [ ] Add Pydantic discriminated command payloads with the exact 8,000-character guidance limit.
- [ ] Add command submit/history routes and preserve the existing cancellation route as a compatibility wrapper.
- [ ] Add session-background and receipt-acknowledgement routes with canonical ownership checks.
- [ ] Start the activity monitor after resource initialization and stop it during orchestrator shutdown.
- [ ] Keep API errors human-readable and redact internal exception details.
- [ ] Run Python bytecode compilation and OpenAPI-import-free syntax checks only; do not start the app or run tests.

### Task 4: Inline subagent control UI

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/agents/AgentTaskTree.tsx`
- Modify: `frontend/src/agents/agents.css`

**Interfaces:**
- Consumes Task 3 JSON contracts.
- Produces accessible steer, stop-subtree, activity-health and durable completion presentation in the existing disclosure.

- [ ] Add command, activity, execution-mode and receipt types plus API methods.
- [ ] Render phase, relative last activity, background state and textual stalled warning.
- [ ] Add a compact guidance form that preserves text on failure and disables duplicate submission while pending.
- [ ] Separate stop-one and stop-subtree intent without a modal; destructive scope must be stated in each button label.
- [ ] Poll only while work is active and stop timers on unmount; refresh final receipts after terminal transition.
- [ ] Use existing theme tokens, 44-pixel targets, keyboard focus, mobile collapse and reduced-motion behavior.
- [ ] Run frontend TypeScript type checking and `git diff --check`; do not run Vitest or build.

### Task 5: Documentation and static integration review

**Files:**
- Modify: `docs/superpowers/plans/2026-09-07-finctrl-3-multimodal-implementation.md`
- Modify: `IMPLEMENTATION_LOG.md`

**Interfaces:**
- Consumes all Stage 18 behavior.
- Produces an honest code-first status with deferred acceptance clearly separated.

- [ ] Append Stage 18 architecture, limits, exclusions, migrations and UI behavior to the master plan.
- [ ] Record implementation and the exact static checks actually run in the implementation log.
- [ ] Inspect migration numbers for uniqueness and run Python compilation, TypeScript checking, and `git diff --check` only.
- [ ] Do not call Stage 18 complete or release-ready until the deferred behavioral test phase is executed.
