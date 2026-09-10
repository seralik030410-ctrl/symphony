# FinCtrl 3.0 Stage 19 — Tool Discovery and Agent Role Routing

## Goal

Reduce tool-schema context cost for small orchestrator models and let delegated roles use explicitly configured provider/model routes without changing the main chat model.

## Tool discovery

FinCtrl exposes a small core set on the first model iteration: `tool.search`, basic file inspection/search, and agent delegation/control. `tool.search` searches only registered tool metadata, returns bounded matches, and activates the returned tools for later model iterations in the same execution. Activation is additive, execution still passes through the existing allowlist and Policy Engine, and tool metadata is never treated as permission.

Main turns and subagents maintain separate in-memory activation sets. Subagents can discover only tools already present in their inherited allowlist. Tool search does not install plugins, access the network, run code, or persist new permissions. If the catalog is small, the hybrid core still applies consistently.

## Role routing

Delegations accept a role from `worker`, `orchestrator`, `code`, `research`, `vision`, `media`, or `review`. Agent settings store optional routes from role to `{provider_profile_id, model}`. Resolution order is explicit task override, configured role route, then current chat provider/model. A route is usable only when its provider profile exists and is enabled; invalid routes fail delegation clearly rather than silently switching providers.

The main chat is never rerouted. Children inherit the resolved provider/model as ordinary immutable task fields, so restart, audit, resource accounting, and UI remain deterministic. Steering cannot change role or route.

## API and UI

Agent settings include `lazy_tools_enabled` and `role_routes`. Settings UI provides a switch and one provider/model selector per role while preserving the existing limits editor. Task-tree rows show the assigned role. No credentials are returned or copied.

## Failure handling and exclusions

- Empty tool queries are rejected; results are capped at 12 and deterministically ranked.
- A model call to a non-activated tool fails normally and cannot activate it implicitly.
- Disabled/missing provider routes reject new delegation; existing tasks retain their stored route.
- No automatic provider failover, MoA voting, plugin installation, remote gateway, or permission expansion is introduced.

## Deferred acceptance

The later verification pass must cover activation boundaries, allowlist isolation, route precedence, disabled-profile rejection, restart persistence, schema-token reduction, TypeScript UI behavior, and full regressions. Stage 19 remains code-complete but not accepted until those checks run.
