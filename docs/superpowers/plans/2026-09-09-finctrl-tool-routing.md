# FinCtrl Tool Discovery and Role Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bounded lazy tool discovery and explicit per-role routing for delegated agents.

**Architecture:** A read-only catalog tool activates registered definitions only inside the current execution. Durable agent settings resolve optional role routes before immutable task creation, while the main chat keeps its selected model.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLite, React, TypeScript.

**Spec:** `docs/superpowers/specs/2026-09-09-finctrl-tool-routing-design.md`

## Global Constraints

- Do not run pytest, Vitest, production builds, migrations, or live providers in this code-first pass.
- Tool activation never changes policy, allowlists, credentials, or installation state.
- Main-chat provider/model selection remains unchanged.
- No automatic failover, MoA, remote gateways, or auto-approval.

---

### Task 1: Durable settings and role contract

**Files:**
- Create: `backend/storage/migrations/0024_agent_tool_routing.sql`
- Modify: `backend/agent/contracts.py`
- Modify: `backend/agent/task_store.py`

**Interfaces:**
- Produces: `AgentRole`, `AgentTaskSpec.role`, settings keys `lazy_tools_enabled` and `role_routes`.

- [x] Add migration columns and task role with constrained defaults.
- [x] Decode, validate, and persist routes without secrets.
- [x] Preserve existing settings defaults during upgrade.

### Task 2: Registered tool discovery

**Files:**
- Create: `backend/tools/discovery.py`
- Modify: `backend/tools/registry.py`
- Modify: `backend/main.py`

**Interfaces:**
- Produces: `ToolSearchTool`, `ToolRegistry.search_catalog(query, allowed_names, limit)`, and filtered `model_definitions(names)`.

- [x] Rank exact name, prefix/token, title, then description matches deterministically.
- [x] Return public definitions for at most 12 registered and allowed tools.
- [x] Register `tool.search` as read-only and side-effect free.

### Task 3: Per-execution activation

**Files:**
- Modify: `backend/agent/turn_service.py`
- Modify: `backend/agent/executor.py`

**Interfaces:**
- Consumes: `ToolSearchTool` output field `activated_tools`.
- Produces: additive execution-local activation sets.

- [x] Start each execution with the hybrid core intersected with its allowlist.
- [x] Recompute schemas before each subsequent model iteration.
- [x] Activate only successful catalog results; never persist activation as authority.

### Task 4: Role route resolution and APIs

**Files:**
- Modify: `backend/agent/orchestrator.py`
- Modify: `backend/tools/delegation.py`
- Modify: `backend/api/agents.py`

**Interfaces:**
- Produces: role-aware delegation and existing settings API extensions.

- [x] Apply explicit override → role route → chat inheritance precedence.
- [x] Reject missing or disabled provider profiles before task creation.
- [x] Return task role through existing tree APIs.

### Task 5: Settings and task UI

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/agents/AgentSettings.tsx`
- Modify: `frontend/src/agents/agents.css`
- Modify: `frontend/src/agents/AgentTaskTree.tsx`

**Interfaces:**
- Consumes/produces: extended `AgentSettings` payload.

- [x] Add lazy-tool switch and bounded role route controls.
- [x] Show role in task rows.
- [x] Preserve accessible labels, mobile layout, and semantic theme tokens.

### Task 6: Documentation and deferred verification record

**Files:**
- Modify: `docs/superpowers/plans/2026-09-07-finctrl-3-multimodal-implementation.md`
- Modify: `IMPLEMENTATION_LOG.md`
- Modify: `pyproject.toml`
- Modify: `backend/main.py`
- Modify: `backend/api/routes.py`

**Interfaces:**
- Produces: Stage 19 scope and version `0.19.0-dev`.

- [x] Record implemented boundaries and exclusions.
- [x] Run Python compilation, TypeScript no-emit, and whitespace checks only.
- [x] Record all behavioral acceptance as deferred.
