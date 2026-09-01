# Symphony 2.0 Product Contract

Symphony is a local-first conversation runtime for direct model chat and an honest record of every external action. Stage 6 keeps the answer primary while adding bounded file retrieval, semantic conversation memory and explicit vision/OCR to trusted documents, skills and the strictly isolated persistent project workspace.

## Product character

- Quiet, direct, dependable.
- Ordinary conversation goes directly to the selected model.
- Tool actions are public, durable, and recoverable. Provider-emitted reasoning traces may be shown verbatim and labelled as model output; Symphony never fabricates or claims access to hidden reasoning.
- A new chat is truly empty: no message, context, action, or file crosses the session boundary.
- Failed and cancelled work can be retried as a new immutable turn.

## Stage 4 action contract

- Only registered structured tools can run.
- Arguments are schema-validated and filesystem paths are confined to the active chat workspace.
- Every call has requested, running, and terminal states plus an audit id and duration.
- Timeout, cancellation, duplicate-call blocking, and bounded repair are first-class behavior.
- The interface exposes arguments, results, changed files, and diff on demand without overwhelming the conversation.
- The interface exposes named stages, provider-reported reasoning, actual token usage when supplied, and configured context-window occupancy for each turn.
- The conversation follows a streaming answer only while the reader remains at the bottom; manual upward scrolling is respected and a clear return-to-bottom action remains available.
- Skills are instructions, never permissions. Only metadata is indexed before selection; full instructions, resources, and scripts are progressively disclosed and each material read/run is persisted in the public trace.
- Skill scripts can run only as registered, approval-gated, offline Docker tools with a read-only skill mount.

## Current exclusions

There is no document or research router. Requested documents use bounded schemas and trusted offline renderers, not model-written renderer code. File actions are scoped to `data/workspaces/{session_id}/worktree`; arbitrary project commands run only inside the Docker sandbox and never fall back to the Windows host. Opt-in research belongs to the host network layer; the macOS release candidate still needs real-device acceptance.

## Stage 5 document contract

- PDF, XLSX, DOCX and PPTX start as schema-validated data. Only successful rendering plus validation publishes an immutable version.
- Source, recipe, output, checksum and validation report belong to one session and survive refresh. Source snapshots and artifacts live outside the generated-code worktree mount.
- A saved artifact event produces a small chat card. Opening it uses the existing docked workspace, never a modal.
- Actual rendered pages and spreadsheet data are visible beside the chat. Validation limitations and unsupported formulas are explicit. Failed/cancelled jobs do not create fake success cards.

## Stage 6 context contract

- File evidence is scoped, hash-checked, bounded and lower priority than instructions. Binary document parsing is offline and isolated; there is no host fallback or silent over-limit truncation.
- Semantic memory comes from the selected model, not sentence prefixes. It has structured fields, versions and source message IDs. Recent messages remain verbatim and the source history remains stored. Users can inspect, correct or clear memory.
- Context limits are per chat. Model capability overrides are explicitly provider/model-wide. Estimates and actual reported usage are distinguished; memory calls count toward turn totals, not current context occupancy.
- A photo requires a compatible vision model; local text OCR is an explicit alternative, not simulated visual understanding. Attachment mode and identity survive Retry and refresh.
- Advanced configuration stays in Settings and collapsed disclosures. Ordinary short chat gains neither a mandatory model planner nor a context dashboard.

## Stage 7 research and desktop contract (in progress)

- Networking is off by default in each chat. The host, not the model or sandbox, enforces public HTTPS and exact-domain permissions. Search always shows the exact outgoing query for approval; permission never transfers to another chat.
- Pages are untrusted evidence. Citations refer to pages actually read, preserve unknown publication dates and show the host check time. Search candidates are explicitly unread. Provider blocking is an error, not a fabricated successful search.
- Internet configuration lives in Settings; saved sources use quiet inline disclosures. Ordinary conversation remains direct.
- Desktop code is a candidate until native compilation and signed MacBook acceptance pass. The local Python server is owned by the shell, and readiness/shutdown/secrets use a private pipe. File-drop tokens grant access only to the explicitly selected bounded files.
- System/light/dark theme and a clean-install dependency kit are implemented and verified on Windows. Native macOS compilation and signed release/update acceptance remain open, tracked in `docs/STAGE_7_STATUS.md`.

## Accessibility commitments

Keyboard-visible focus, semantic controls, readable contrast, 44-pixel primary targets, reduced-motion support, status text that does not rely on color, and responsive layouts from 375px upward are required.
