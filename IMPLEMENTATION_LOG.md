# Symphony 2.0 Implementation Log

This log is updated only after a stage has a concrete implementation and verification evidence.

## 2026-08-29 - Stage 0 complete

- Created a clean project in `C:\Users\alijo\Documents\Codex\2026-08-29\symphony2`.
- Kept the legacy application at `C:\Users\alijo\Documents\anush` read-only.
- Copied the complete rebuild specification to `docs/SYMPHONY_2_REBUILD_SPEC.md`; source and copy have the same SHA-256 hash.
- Recorded an aggregate, content-free legacy baseline in `tests/evals/legacy-baseline.json`.
- Established independent backend, frontend, storage, migration, test, and documentation boundaries.
- Explicitly excluded document routing, skills, tools, artifact generation, and sandbox behavior from Stage 1.

Verification: filesystem boundary and source-document hash checked locally.

## Stage 1

## 2026-08-29 - Stage 1 complete

- Added independent session, message, and turn records with deterministic per-session message ordering.
- Added ordered typed events, SQLite WAL, two file-based migrations, and restart interruption recovery.
- Added a bounded 16K-default context builder that queries one session only.
- Added one Model Gateway contract and streaming adapters for Ollama and OpenAI-compatible chat APIs.
- Added direct background turn execution with persisted text deltas, SSE replay, provider cancellation, partial-answer preservation, and final states.
- Added FastAPI endpoints for session creation/listing/update, turns, cancellation, event replay/streaming, model profiles, and health.
- Added a React + TypeScript interface with Markdown/GFM rendering, session switching, model selection, Stop, refresh recovery, responsive layout, explicit error/empty/loading states, and a ledger of persisted runtime events.
- Kept document routing, skills, tools, artifact generation, file access, and sandbox code absent from the Stage 1 request path.
- Added unit and integration coverage for migrations, token budget, strict session isolation, direct-chat event types, refresh recovery, Stop, and Ollama/API contract parity.

Verification evidence:

- `python -m pytest`: 9 passed.
- `npm test`: 2 passed.
- `npm run build`: production assets generated in `frontend/dist`.
- Browser QA: verified at 375, 768, and 1440 px; fixed two responsive overflow defects found during the review.
- Runtime QA: the production build served from FastAPI, persisted a real offline-provider failure, restored it after reload, and showed the matching event ledger with no browser console errors.
- Static architecture gate: no document router, artifact detector, sandbox runtime, or skill registry exists in the Stage 1 backend.

## 2026-08-29 - Stage 2 complete

- Added an explicit Tool Registry and shared structured-call contract behind the existing direct-chat lifecycle.
- Extended both Ollama and OpenAI-compatible adapters with native structured tool-call streaming while retaining incremental text streaming.
- Added a bounded model/tool loop with a 12-call default limit, identical-call blocking, validated arguments, failure observations for model repair, per-call timeout, and cancellation propagation.
- Added migration `0003_tool_calls.sql` and durable audit records with requested, running, completed, failed, and cancelled states, audit ids, results, errors, and durations.
- Added per-session worktrees and blocked absolute/drive/ADS paths, traversal, workspace escapes, and cross-session reads.
- Implemented `fs.list`, `fs.read`, `fs.write`, `fs.apply_patch`, and `search.rg` for UTF-8 text workspaces; file mutations report unified diffs and changed paths.
- Added persisted and streamed public events for every action and file change, plus workspace-tree and tool-discovery endpoints.
- Added Retry as a new immutable turn for failed, cancelled, or interrupted work.
- Added inline expandable action rows to the assistant message with textual status, duration, arguments, result, changed files, and diff; extended the event ledger with the same durable activity.
- Kept ordinary conversation direct: the no-tool acceptance scenario emits only context/model/turn events and no document, skill, sandbox, artifact, or tool activity.
- Updated README, product contract, design direction, environment defaults, package metadata, and stage labels.

Verification evidence:

- `python -m pytest`: 17 passed.
- Provider contract tests: native Ollama calls and fragmented OpenAI-compatible tool arguments parsed successfully.
- Stage 2 acceptance test: a model created two files, patched one in a later step, and completed with three audited calls and three file-change events.
- Stop test: cancelling during an active tool persisted both `tool.cancelled` and `turn.cancelled` terminal states.
- Workspace tests: create/read/patch/search/list, traversal rejection, chat isolation, and timeout all passed.
- `npm test`: 2 passed.
- `npm run build`: TypeScript and Vite production build succeeded.
- Browser QA: completed a real two-step file action through the production UI, expanded arguments/result/diff, reloaded and recovered two action cards, and found no console errors.
- Responsive QA: no horizontal overflow at 375, 768, or 1440 px; mobile hides rails, tablet keeps the chat rail, and desktop shows the full event ledger.
- Static architecture gate: no document router, skill registry, sandbox, shell execution, or arbitrary code execution was added.

## 2026-08-29 - Stage 3 complete

- Added migration `0004_sandbox_approvals.sql`, per-session policy profiles, and durable pending/approved/denied/cancelled approval records tied to audited tool calls.
- Added a reproducible Node 22 + Python 3 runtime image and a Docker executor with a read-only container root, no-new-privileges, all capabilities dropped, resource/process limits, bounded output, timeout cleanup, and network disabled by default.
- Mounted only `data/workspaces/{session_id}/worktree` into `/workspace`; the worktree persists between commands while separate chats remain isolated. No host command fallback exists.
- Added `sandbox.shell` for Python/Node tests and builds, plus `sandbox.preview` and a read-only per-session preview route for generated HTML and relative assets.
- Added strict, restricted, and trusted policy profiles. Restricted mode requires one-time user approval for installs, network, and destructive commands; hard-denied device/host capabilities remain blocked in every mode.
- Streamed and persisted approval and preview events alongside tool output, stderr/stdout, changed files, duration, errors, and final states. Stop cancels pending approvals and the active execution path.
- Replaced native model/session selectors with a reusable accessible custom combobox supporting keyboard navigation, grouping, unavailable states, and responsive menus. Added the same component for sandbox policy selection.
- Added inline approval decisions and preview links to the chat, plus approval/preview entries in the durable event ledger.
- Kept ordinary conversation on the direct Model Gateway path; document routing, skills, and document generation remain absent.

Verification evidence:

- `python -m pytest`: 26 passed.
- Stage 3 acceptance tests: a scripted model created source, ran a build, persisted `dist/index.html`, emitted `preview.ready`, and served the preview through the session-scoped route.
- Approval test: a networked install stayed blocked before an explicit API decision, then executed only after approval; both decision events were persisted.
- Isolation test: a preview created in one chat returned 404 from a second chat.
- Policy tests: restricted prompt, strict deny, trusted allow, hard deny, and safe no-prompt paths passed.
- Runtime contract tests: verified no-network default, read-only root, dropped capabilities, no-new-privileges, bounded single-workspace mount, temporary caches, and approved network opt-in flags.
- `npm test`: 2 passed.
- `npm run build`: TypeScript and Vite production build succeeded.
- Docker CLI was present, but the local Docker Desktop daemon was not running during final verification. The runtime therefore correctly reported unavailable and never fell back to host execution; the image build command is `scripts/build-runtime.ps1` once Docker Desktop is started.

## 2026-08-29 - Stage 3 conversation observability and launcher hardening

- Fixed the conversation grid so the conditional error row no longer displaced the history/composer rows; the composer now stays at the bottom and the history owns the remaining viewport height.
- Replaced document-level `scrollIntoView` with explicit conversation-container follow state. New turns jump to the bottom, streaming remains pinned while the reader is at the bottom, manual upward scrolling is respected, and a `Вниз` control restores follow mode.
- Added a visible, keyboard-focusable scrollbar with stable gutter to the chat canvas.
- Extended the Model Gateway stream with provider reasoning and token usage events. Ollama enables `think`, reads `message.thinking`, `prompt_eval_count`, and `eval_count`; OpenAI-compatible APIs read common reasoning fields and request streaming usage.
- Added Ollama `/api/show` context-window discovery with per-model caching. The installed `qwen3.5:9b` reported a 262,144-token window.
- Added an inline assistant-turn progress strip with named stages, expandable provider reasoning, context occupancy, cumulative sent tokens, and cumulative received tokens. All data survives refresh through durable events.
- Added `START.bat` and `scripts/start-all.ps1` to bootstrap missing dependencies, start Docker Desktop, build the sandbox image once, start Ollama, build changed frontend sources, start FastAPI, and open port 8765.

## 2026-08-30 - Stage 3 chat presentation and verified scrolling fix

- Reproduced the remaining scrolling bug against the previous production build: at a 900px viewport, the shell was 900px but its implicit grid row/conversation pane grew to 4440px. History `clientHeight` equalled `scrollHeight` (4266px), so there was no internal scroll range; the composer was outside the screen. The preceding grid-row adjustment alone was insufficient.
- Set an explicit viewport block size and `minmax(0, 1fr)` shell row. Replaced the conversation's conditional-row grid with a flex column containing fixed header/composer and one bounded history viewport. After correction: page/pane 900px, history viewport 726px, content 3770px, composer bottom 900px.
- Separated user follow intent from content resizing. ResizeObserver handles streaming, disclosures, wrapping, and composer size. Upward wheel/touch/keyboard reading pauses following; send/retry and the down-arrow restore it. Home/End/PageUp/PageDown/arrow keys work on the focused history region. The return arrow stays above a multiline composer.
- Replaced the stage-chip strip and token dashboard with a quiet status/reasoning disclosure above the answer and a compact expandable usage line below it. Reasoning uses readable text in the normal history flow, not another scroll box, and incoming fragments never reopen it. Detailed metrics distinguish cumulative per-turn token usage from the latest model call's input context.
- Added deterministic, in-memory `scripts/ui-fixture.mjs` (port 8766) for testing the actual built frontend without user data, model calls, Docker, or a database. Production's port remains 8765. Updated README and DESIGN.md.

Verification:

- `npm test -- --configLoader runner`: 11 tests passed, including 5 scroll-controller regressions and 4 usage/stage tests.
- `npm run build -- --configLoader runner`: TypeScript and production build succeeded. `npm run typecheck` also passed. The runner config loader avoids the config bundler's ancestor-directory access failure in this restricted Windows session.
- Browser: wheel up changed history position by 600px; return arrow restored the bottom. During streaming, history grew from 7212px to 9933px while manual scrollTop remained exactly 5986px. Reasoning remained collapsed after subsequent deltas. Home moved to 0, PageDown moved to 617px, End restored a zero bottom gap.
- Browser: widths 375/768/1440 had no document overflow, and the composer stayed at the viewport bottom. Verified expanded reasoning/usage, a simulated error banner, empty-chat isolation, and active-turn restoration after refresh against the fixture API.
- Scope/limits: no backend or legacy application changes in this pass. Real FastAPI/Ollama/Docker startup and Python tests were not rerun: the installed Python executable is denied in this session, and the bundled Python lacks FastAPI with package-download access restricted. Browser evidence above is explicitly from the isolated fixture, not a live model.

## 2026-08-30 - Stage 3 closeout: real runtime acceptance and docked workspace

This entry supersedes the earlier Stage 3 completion claim's verification limits. The original scripted acceptance remains useful, but it did not prove a working local Docker/Ollama installation. That missing live check is now complete. Stage 4 has not been started.

- Built and ran runtime image version 3.1: Python 3.12 + Node 22, pytest, git, ripgrep, curl, Poppler and office libraries. Fixed Windows subprocess flags, scoped orphan cleanup to this installation, bounded stdout/stderr streaming, and verified Stop/timeout process-tree removal with real containers.
- Added transactional migration execution, migration 0005 canonical Read only / Project edit / Build / Full manual permission profiles, explicit one-call approvals, active-turn setting locks, offline build classification and a two-repair limit after an initial tool failure.
- Added content-addressed source snapshots before mutating calls; storage sits outside the container mount. Added audited `project.snapshots` / approval-gated `project.restore`, pre-restore safety snapshots, size limits, link/junction rejection and unique atomic-write temporary paths.
- Fixed context budgeting: configured 16K is actually sent to Ollama, tool instructions/schema budget is included, large observations are bounded, and cumulative token totals are not mistaken for active context occupancy. New chats select an installed local Ollama model if the configured default is absent.
- Hardened preview: sandboxed opaque origin, JavaScript/module assets work but storage/API access, network, forms and browser modals are blocked. No host-shell or unconfined preview fallback.
- Added migration 0006 recoverable session trash. Deleting an active chat cancels its turn first; messages/events/worktree/snapshots remain recoverable. Added confirmation, undo and trash restoration in the UI. Delete icons are permanently visible instead of hover-only.
- Replaced the initial preview modal after the user's clarification with a resizable docked workspace. Tabs cover Preview, Files, source code and snapshot Changes; + adds a chooser, × closes a tab, keyboard navigation is supported, and per-chat tabs/active selection survive refresh. Event ledger and workspace share the right inspector area.
- Added read-only file/diff APIs, bounded large/binary output, syntax-coloured escaped source with line numbers/copy, unified and two-column snapshot comparison. Changed-file entries open source tabs. No editor/save or Git commit feature is implied.
- Corrected the reported ambiguous Files action: it now opens a named Files tab, not a generic New tab. Revealed the active tab when the strip overflows and fixed rail branding layout after adding its close control.
- Guarded late send/retry/model/policy responses against rendering into a newly selected chat. Retained the bounded conversation scroller and visible composer.
- Updated README, DESIGN.md and `docs/STAGE_3_ACCEPTANCE.md`; launch remains `START.bat`, frontend/API at port 8765. Launcher recognizes the cached runtime version instead of rebuilding on every start.

Verification evidence:

- **49 backend tests passed**, including six opt-in real Docker tests; **17 frontend tests passed**; TypeScript and Vite production build passed. Python 3.14 pytest-asyncio deprecation warnings remain non-failing (325 warnings in the last full run).
- Real Ollama `qwen3.5:9b` at 16K created the coffee site from the natural-language request, wrote six source files, ran ten generated assertions and the build inside Docker after reviewed one-time approvals, and served HTML/CSS/JS successfully. Turn `62dd75c73c4e4841a395275e7ab2d65d` completed in 238.344s. Detailed evidence and the earlier failed attempt/verifier correction are documented in the acceptance report.
- Browser QA on the production UI: docked preview, code/diff tabs, restore after reload, named Files tab, chat isolation, deletion and restoration of a synthetic QA chat, and independent scrolling. 375/768/1440px layouts have no horizontal document overflow; mobile uses a full-area workspace with a return control. Home/PageDown/return-to-bottom retain a real history scroll range and visible composer.
- The QA chat temporarily moved to trash was restored. No user chat or legacy application file was removed. Only the superseded modal component created during this implementation was removed from source.

Remaining product stages: Skills 2.0 (Stage 4), documents, structured memory, research and subsequent features. Local-only authentication assumptions, static preview restrictions, bounded file/diff sizes and snapshot retention limitations are explicit in the README/acceptance report.

## 2026-08-30 - Stage 4 complete: Skills 2.0 and Settings

- Added migration 0007 and a managed skill store with a metadata-only index, bounded deterministic matching, Explicit / Auto / Always / Off activation, priority, manifests/dependencies, validation, atomic edits, export, and recoverable trash. ZIP/local-folder/HTTPS-Git installers reject traversal, links/junctions, archive bombs, duplicate slugs, credential-bearing URLs, invalid manifests, and oversized instruction files.
- Implemented progressive disclosure. Ordinary unrelated chat receives no skill suffix or skill events. After activation the host reads full `SKILL.md`; references remain outside the initial prompt and are exposed only by the registered `skill.read_resource` tool.
- Added approval-gated `skill.run_script` for `.py`, `.js`, and `.sh` below `scripts/`. Scripts run offline in the real Docker sandbox, with the skill mounted read-only and only the active chat workspace writable. Installation never executes code, and a skill never grants permissions.
- Persisted and streamed `skill.cataloged`, `skill.selected`, `skill.read`, `skill.resource_read`, and `skill.script_executed`. Added a compact inline disclosure proving which instructions/resources/scripts were actually used, plus named skill stages and event-ledger entries.
- Added a full-screen Settings surface inspired by the app's quiet navigation pattern. Permissions and model configuration live under General; Skills provides install, index/search, activation, priority, `SKILL.md` editor/validation, resource reader, dependency metadata, test prompt, export, delete, and restore. Removed the second chat-sidebar hide control and redundant chat-toolbar delete/diff actions.
- Added the bundled `Static site quality` example skill, updated README, product/design contracts, environment defaults, and `docs/STAGE_4_ACCEPTANCE.md`. The original rebuild specification remains copied under `docs/`; the legacy application was not changed.

Verification evidence:

- **50 backend tests passed** with **7 real-container tests skipped** in the default run. With `SYMPHONY_RUN_DOCKER_TESTS=1`, all **7 Docker tests passed**, including the new read-only skill mount/offline/workspace-scoping case.
- **17 frontend tests passed**. TypeScript and the Vite production build passed; the only build note is Vite's non-failing 500 KB chunk-size warning.
- Live Ollama acceptance on `qwen3.5:9b`: QA turn `86e584ee0c424ec9829c58971fde92ca` completed and durably recorded `skill.selected → skill.read → tool.requested → skill.resource_read → turn.completed`. The checklist was absent from the initial prompt and appeared only after the resource tool result.
- Production browser QA showed the full trace with no console errors. Settings and Skills were inspected on desktop and 375×812; the narrow document had `scrollWidth === innerWidth` and all controls remained reachable. The running app remains at `http://127.0.0.1:8765`.

Remaining product stages: document routing/generation, structured memory, research, and subsequent features. Stage 4 does not add any document router, sandbox bypass, host-shell fallback, or hidden skill execution path.

## 2026-08-30 - Stage 4 library import and installer closeout

- Audited the supplied `skill_for_s` tree: 37 `SKILL.md` files, 884 files / 32.38 MB, 31 unique skill instruction sets and six exact duplicate packaging copies. Installed all 31 unique skills in Explicit mode; no imported code ran.
- Preserved 21 oversized upstream instruction documents verbatim as progressively-read managed references while keeping the indexed `SKILL.md` below 8 KB. Direct editor validation remains strict.
- Exercised all three installer paths through the production Settings UI. Folder and ZIP imports passed, including a nested resource. HTTPS Git installed an official repository subdirectory through `repo.git#path/to/skill`.
- The live Git run found and fixed Windows read-only `.git` pack cleanup. Added sparse clone/checkout for repository subdirectories, credential/path validation, regression coverage, and folded YAML frontmatter-description parsing.
- Loaded and validated every active skill through the API, read all 21 progressive full-instruction resources, and tested deterministic `$slug` activation for every entry: zero failures. Disposable QA entries were purged; the active catalog is 31 supplied skills plus the bundled example.
- Added `docs/SKILL_LIBRARY_AUDIT.md` with per-skill file counts, prompt form, executable-helper exposure, duplicate handling, and the special authorization warning for the pentesting skill.

Verification evidence:

- **53 backend tests passed**, **7 opt-in Docker tests skipped**; **17 frontend tests passed**; TypeScript and Vite production build passed. The only build note is Vite's non-failing 500 KB chunk warning.
- Production API inventory: 32 active, 31 Explicit, 21 normalized imports, 11 entries with scripts including the bundled example, zero validation/activation failures.

## 2026-08-30 - Stage 5 complete: trusted documents

- Added migration `0008_artifacts.sql` and an immutable per-chat artifact store with atomic version publication, source/recipe/validation provenance, SHA-256 verification on download, recoverable chat-trash behavior, and strict cross-chat ownership checks.
- Added strict bounded Pydantic schemas and fixed trusted renderers for PDF, XLSX, DOCX and PPTX. The model writes structured JSON only; it never writes or executes renderer code. PDF pages are inspected with PyMuPDF, DOCX/PPTX previews are converted from the actual native files with LibreOffice, and XLSX files are reopened and independently checked.
- Added a non-evaluating spreadsheet formula interpreter for bounded arithmetic and `SUM`, `AVERAGE`, `MIN`, `MAX`, `COUNT`, `ABS`, and `ROUND`; cycles, invalid/out-of-data references, external links, DDE, macros and unsupported formulas fail validation.
- Added `artifact.schema`, `artifact.render`, `artifact.inspect`, and `artifact.read_table` to the existing model/tool loop. Ordinary chat remains direct and emits no document/tool activity. Failed validation returns a bounded repair observation; unchanged duplicate calls remain blocked while a genuinely changed source can be rerendered as a new version.
- Added an offline production document worker with a single writable staging mount, read-only trusted renderer code, no chat worktree or host-home mount, non-root execution, dropped capabilities, read-only root, resource limits, timeout/Stop cleanup and no host fallback. Cancelled/failed jobs publish no successful artifact.
- Added session-scoped XLSX/CSV/JSON/PNG imports and bounded table reads. Added docked document tabs, inline artifact cards, version switching, real page/table previews, downloads, provenance/validation disclosures and independent mouse/keyboard scrolling. Tabs restore after refresh and remain usable at 375 px without document overflow.
- Updated the Windows launcher to install required libraries and rebuild runtime label 5.0 when necessary. Added the acceptance report, UI fixture and live Ollama verifier.

Verification evidence:

- **97 backend tests passed** with real Docker coverage enabled, including all four native formats, LibreOffice conversion, formula security/repair, versioning, integrity, cancellation/container cleanup, upload bounds, ordinary-chat parity and strict chat isolation.
- **20 frontend tests passed**. TypeScript and the Vite production build succeeded; the only build note is Vite's non-failing 500 KB chunk-size warning.
- Live Ollama `qwen3.5:9b` acceptance at 16K completed through the normal tool loop without automatic approval. Session `0368c9875d1a475bb9b3ac125476034e` created and downloaded PDF artifact `e0e431c80ca5405c86758edbbde8b88d` and XLSX artifact `5cc7243b71b84f73b5fa5a54622c70f7`. Machine-readable evidence is in ignored `data/acceptance/stage5-live-0368c9875d1a475bb9b3ac125476034e.json`.
- Production browser QA verified PDF/XLSX/DOCX/PPTX previews, version switching, refresh recovery, docked scrolling, return-to-chat behavior and mobile layout against an isolated data store.

Remaining product stages: Stage 6 retrieval/structured memory/OCR/vision and Stage 7 research/macOS packaging. Stage 5 adds no keyword document router, hidden fallback document generation, OCR, semantic memory, web research or desktop packaging.

## 2026-08-31 — Stage 6 in progress; context controls verified

Stage 6 is **not complete**. This entry is a progress record, not an acceptance sign-off.

- Added migration 0009 and initial per-session attachment/index/FTS/manual-memory services, attachment previews and source disclosures. Pending uploads are not implicitly retrieved before sending. Retrieved content and manual memory use a lower-priority evidence message, not the system instruction message.
- Added Settings → Контекст и память → Лимиты модели: 8K/16K/32K/64K presets and a response-token limit. Changes persist per session, validate the selected model's ceiling and output/window relationship, and are rejected during an active turn. Model switches clamp an oversized context to the new provider ceiling. Ollama receives num_ctx/num_predict; compatible API requests receive max_tokens with a local request budget.
- Added 9 parametrized API cases plus 2 frontend tests, including persistence, cross-chat independence, provider propagation, invalid values, active-turn locking and model switching. Adapter HTTP tests check the actual payload options.
- Removed the provisional prefix/sentence-based auto-compaction: it does not satisfy the specification's semantic memory requirement. Automatic snapshot requests explicitly return 501 for now. Manual notes are versioned and never claim coverage of or replace source history. Stage labels and both brief TXT files now say Stage 6 is in progress.
- Ollama vision discovery now uses advertised `/api/show` capabilities rather than model-name guesses. Arbitrary compatible-API vision is disabled pending explicit capability profiles. The OCR Docker layer is prepared separately from the cached office layer; its download/build was stopped before completion. Existing trusted documents remain compatible with the already-installed runtime 5.0, and renderer validation also accepts the forthcoming 6.0.
- New-UI/old-backend compatibility keeps chat loading and legacy attachment uploads usable. The new settings report that a backend restart is needed instead of silently pretending to apply unavailable controls.

Verification:

- Full run with `SYMPHONY_RUN_DOCKER_TESTS=1`: **112 passed** on the existing runtime 5.0. OCR's new tests currently mock the sandbox contract; this is not a live OCR/vision acceptance result. 631 dependency deprecation warnings are non-failing.
- Frontend: **22 passed**; TypeScript and Vite production build successful. The existing non-failing 500 KB bundle warning remains.
- Isolated browser QA on port 8769 with a separate database: saved 32K/4096, reloaded, reopened Settings and verified persistence; inspected 1440, 768 and 375 px layouts without document horizontal overflow.
- The main port 8765 still had backend 0.5.0. Its automatic restart was blocked by the environment before execution; user permission was requested. No active user turns were found, and no user chat was stopped or deleted. A frontend rebuild alone does not restart Python.

Remaining Stage 6 work and runtime/release status are explicitly listed in `docs/STAGE_6_STATUS.md`. Do not advance to Stage 7 or claim the whole specification is implemented.

### 2026-08-31 — Authorized restart still blocked

The user explicitly approved restarting Symphony. Reconfirmed the listener belongs to this project's backend PID 17152 and no turns are active. The environment again rejected the restart command before execution. A subsequent health check still returned Stage 5 (`documents`); no restart or data deletion occurred. A manual restart is needed; no alternative was used to bypass the restriction.

## 2026-08-31 — Stage 6 complete: context, retrieval, semantic memory, vision/OCR

- Completed the Stage 6 contract from the unchanged rebuild specification. Migrations 0009–0012 cover scoped file chunks/attachments, memory provenance, reusable immutable attachment associations for Retry, and explicit provider/model capability overrides. Stage 7 has not been started.
- Implemented real structured summarization through the selected model and the existing Gateway, not prefixes of old messages. Whole-message batches merge Facts, Decisions, Open tasks and Artifact index. Automatic compaction starts near 72% of available input budget; at least ten recent messages stay verbatim. Original messages remain in storage. JSON validation, source IDs controlled by the host, version checks, cancellation and busy guards prevent partial or conflicting publication. Users can manually compact, edit, clear and inspect versions.
- Unified the preflight text/image estimate and reserved schemas, evidence, memory, output and tool results. Recent messages that still do not fit fail explicitly instead of being silently cut. Memory usage contributes to turn totals, not current-call context occupancy. Estimates remain labelled estimates; provider-reported usage remains authoritative.
- Added scoped FTS5 retrieval with bounded chunks, hash freshness checks and user disconnect/reindex controls. Pending uploads do not enter retrieval before send. PDF/DOCX/PPTX/XLSX extraction uses a trusted worker in a separate offline, read-only, non-root container with a copied input only, no workspace/home mount, resource/output/archive limits, timeout and cancellation cleanup. Fixed a real PDF-parser protocol failure caused by a deprecated `fitz` import writing a warning to stdout; switched to `pymupdf` and isolated parser output from the JSON protocol.
- Completed multi-file/image attachments, batch upload busy state, refresh restoration, eight-file limit, image-only sends, scoped previews and pending deletion. Retry preserves the original attachment identity and vision/OCR mode; sent files cannot be deleted as drafts and modified bytes fail SHA-256 validation.
- Added actual vision routing from Ollama metadata and explicit persistent overrides for unknown API capabilities, with reset and model-wide scope explained in Settings. Local Tesseract OCR is a registered, audited offline tool and can feed text-only models. Vision images are sent only with the active turn. Runtime image label 6.0 is built and used; there is no host OCR/parser fallback.
- The designer-skill workflow kept advanced settings in quiet disclosures, without adding a chat dashboard. Browser review found that `justify-items: start` narrowed native details content; resetting it to stretch fixed the memory editor on desktop and mobile. Busy memory fields are disabled. Existing composer/scroll behavior remains intact.
- Updated README, PRODUCT.md, STAGES.txt, ЭТАПЫ_SYMPHONY.txt and docs/STAGE_6_STATUS.md with actual completion, controls, reproducible tests and limitations. The architecture source SHA-256 matches the original exactly: `EC12A8C63460D9C3F4D404BA2933C3213BA73D6039DB85426C8753D9C302DE79`. The legacy application was not modified.

Verification:

- Final full run: `SYMPHONY_RUN_DOCKER_TESTS=1 .venv/Scripts/python -m pytest -o addopts='' -q --disable-warnings` — **132 passed**, 739 non-failing dependency warnings, 73.81 seconds. Includes native extraction of all four document formats, container cancellation, ZIP/output limits, malformed memory output, context overflow, isolation, capabilities, image/OCR Retry, attachment integrity and prior-stage regressions.
- Frontend: **26 passed**; TypeScript and Vite production build succeeded. Added regression coverage for memory-model token totals versus current context. The existing non-failing >500 KB JS chunk warning remains.
- Real Docker + Ollama `qwen3.5:9b`: large DOCX indexed into 37 chunks; request received at most 6,000 source characters and answered code 73421; OCR read TOTAL 42 USD; vision identified a blue rectangle and 42; semantic memory preserved Lumen/SQLite/network restriction/pending release check from beyond the old prefix boundary and recorded 14 source IDs. Ordinary new chat used no tools/retrieval. Reproducible command: `python -m scripts.verify_live_stage6`; successful report: `data/acceptance/stage6-804a4025f9/report.json`. Test data is separate from user chats. OpenAI-compatible was contract/HTTP tested; no paid live-provider check is claimed.
- Browser QA with a separate DB on 8769: memory save/clear/version history and reload, pending thumbnail recovery, OCR-mode image-only send, saved events after refresh, history Home/End with visible composer. At 375/768/1440 px, document scroll width matched viewport; opened memory editor widths were 299/483/863 px without internal horizontal overflow. The viewport override was reset and the QA backend was gracefully stopped.
- During the final check the earlier 0.5.0 server was no longer listening on 8765. No blocked termination operation was bypassed. Started the new production backend on the free port with unique log files; `/api/health` and OpenAPI report **0.6.0**, sandbox is ready and `/` serves the verified `index-VNxv_zWh.js` / `index-RwUmCrMS.css` build. Main browser opens `http://127.0.0.1:8765`; existing user chats remain in the production store.

Limits: lexical rather than embedding retrieval; approximate preflight token/image costs; model-derived memory can lose nuance and is editable; bounded input/extraction sizes; scanned PDFs need page-image OCR rather than automatic whole-PDF OCR; no automatic retention expiry. Stage 7 research, network allowlist and macOS packaging remain pending.

## 2026-09-01 — Stage 7 in progress: research, diagnostics and desktop candidate

Stage 7 is **not complete**. Native compilation and release acceptance have not run, and implementation items remain. The copied specification is unchanged (SHA-256 `EC12A8C63460D9C3F4D404BA2933C3213BA73D6039DB85426C8753D9C302DE79`). The legacy application was not modified.

- Added migration 0013, scoped research settings/source storage, registered `web.search`/`web.open` and durable request/response/source events. Networking defaults off per chat. Exact search queries always require approval; unknown page domains receive one-call approval. Allowlisted page reads validate public HTTPS, DNS/IP and every redirect; pinning checked IPs preserves TLS hostname verification. No inherited proxies/cookies, local addresses, credentials, binaries, compressed bodies or unlimited responses. Pages are bounded untrusted evidence, not instructions or permission.
- Added Internet settings, emergency disable, persisted source disclosures with unknown-publication handling and actual check times, plus privacy-minimal diagnostics JSON/ZIP. Existing designer-skill guidance kept these controls in Settings/collapsed sources instead of adding another chat dashboard. Ordinary chat still has no document/research router.
- Wrote Tauri shell, exact-main-URL capabilities, OS secret-store commands, private-pipe bootstrap/readiness/shutdown, explicit startup-error page, HTTPS external opener, updater controls and native drop tokens backed by selected file handles. Fixed occupied-port startup before database initialization and multi-file uploads interrupted by React rerenders; async chat switches cannot append another chat's upload. Saving/removing a key explicitly requires restart. Python/TypeScript behavior is tested; Rust remains uncompiled.
- Added macOS prerequisite/build scripts and CI candidate. It freezes actual migrations, frontend and trusted Docker-worker sources; tests the real frozen binary instead of using a dummy sidecar; uses an isolated build venv and npm-locked CLI. Generated icon assets from a checked-in SVG. Signing/notarization/update configuration must be provided by the release owner. No release identity, endpoint or private key was fabricated.
- Bounded Windows launcher Docker probes after observing a hung named pipe. `START.bat` can eventually continue with ordinary chat even when Docker fails.

Verification:

- Final backend with `SYMPHONY_RUN_DOCKER_TESTS=1`: **184 passed, no skips**, 937 non-failing dependency warnings, 82.32 seconds on actual Docker runtime 6.0. Earlier unavailable-Docker run: 167 passed / 17 skipped, 42.78 seconds; superseded by this complete run.
- Frontend: **33 passed**, TypeScript and Vite production build successful; existing >500 KB main-chunk warning remains. Native-drop tests cover batching, switching during consume/upload, and failure propagation; source rendering rejects executable URLs and escapes text.
- Sidecar Python suite: **11 passed**, included above. Checks invalid/bounded bootstrap, no key leakage, port conflict with no database creation, readiness after startup, and clean command/EOF shutdown. Source Python is not proof of a compiled native application.
- Live Ollama `qwen3.5:9b` read `https://docs.python.org/3/library/asyncio.html` through real `web.open`, returned its actual URL/check time and saved source/events. A new chat had no sources and disabled networking. The separate live search attempt returned HTTP 202; it failed explicitly, with no fabricated results/fallback. Overall live report is **not fully passing**: `data/acceptance/stage7-68f50f2ca9/report.json` has `ok: false`. Reproduce with `python -m scripts.verify_live_stage7` (isolated QA database, fixed public query).
- Earlier isolated browser QA verified Internet save/reload and 375 px layout with no horizontal document overflow. Final browser QA opened the actual General/Internet settings and checked default-off controls and diagnostics without changing user permissions; no console errors were recorded. Main runtime was started on free port 8765, reports **0.7.0-dev / research**, and serves `index-BD9cBl0B.js`. Existing production chats were not deleted or reset.

Cache/environment:

- Cleared approximately 1.08 GiB of npm package cache, 49.4 MB of pip cache and Docker build cache reported as 3.08 GB reclaimable. Model weights, images, volumes, user chats, installed skills and project files were preserved. Package/build caches can be downloaded/regenerated. Direct deletion of the bundled runtime/npx directories was denied by the execution policy and was not bypassed.
- Offline Docker VHD compaction was attempted but Windows denied it; no successful physical VHD shrink is claimed. The later free-space reading was **66.42 GiB** on C: (a current measurement, not attributed entirely to this cleanup).
- Docker Desktop subsequently failed at startup on its zero-byte `dockerInference` socket (`The file cannot be accessed by the system`). Stopped only the failed Desktop process tree started for this check. Renaming that exact temporary socket also failed; no reset, image/volume removal, privilege change or alternate deletion method was used. During final UI/diagnostic checks Docker became available again (engine 29.7.2, runtime label 6.0); the agent did not successfully repair/remove that socket. The subsequent real-container regression run passed all 184 tests. Docker, Ollama and Symphony chat are available at handoff.

Remaining: reliable live search, system light/dark theme (§15.4), clean-install desktop dependency/runtime-image setup, actual macOS compile/freeze/package and bundled worker validation, verified dependency lock, Keychain/native-drop acceptance and a signed/notarized installer/update test. See `docs/STAGE_7_STATUS.md`; do not mark Stage 7 complete.
## 2026-09-01 — Stage 7 continuation: themes and clean-install runtime path

Stage 7 remains **in progress**. The copied architecture source still matches the legacy source exactly (SHA-256 `EC12A8C63460D9C3F4D404BA2933C3213BA73D6039DB85426C8753D9C302DE79`); the legacy application was not modified.

- Added system/light/dark application themes through semantic roles, an early no-flash bootstrap, live OS preference observation, cross-window restore and graceful storage failure. The selector stays in General settings rather than adding chat clutter. Dark mode covers chat, settings, traces, workspace and artifact chrome while preserving document/site content colors.
- Added a standalone runtime 6.0 ZIP endpoint and quiet dependency disclosure in Diagnostics. The kit includes the exact packaged Docker recipe, requirements, instructions, SHA-256 manifest and confirm-before-build PowerShell/Bash launchers. It requires Docker Desktop but no project checkout or host Python/Node/Git, explains disk/network cost, verifies extraction before building, and never deletes data/cache/models/volumes.
- Bundled `runtime-image` into the frozen sidecar resources. Diagnostics no longer instructs an installed macOS user to build from a source checkout. Official Docker Desktop and Ollama download links were checked on 2026-09-01.
- Automated verification: **195 backend tests passed with `SYMPHONY_RUN_DOCKER_TESTS=1`, no skips**; **42 frontend tests passed**; TypeScript and Vite production build passed (existing non-failing >500 KB chunk warning). Setup tests run the extracted kit through real Windows PowerShell and real Bash/shasum inside an offline, read-only, capability-dropped Docker container while mocking only the external Docker build operation.
- Browser verification used production assets and an isolated document fixture: settings/chat/workspace/PDF at 1440, 768 and 375 px, no document horizontal overflow, theme restore works, PDF paper remains light. The temporary viewport was reset and fixture stopped. Production backend was safely restarted with zero active turns; health is OK, Docker runtime is ready, and `/api/setup/runtime-kit` returns the expected ZIP.

The original DuckDuckGo HTML endpoint returned HTTP 202, so the same approved query now uses DuckDuckGo's lightweight HTML endpoint rather than a hidden second provider or CAPTCHA bypass. Parser coverage accepts both documented result class shapes and still rejects unsafe links. Security/integration checks passed; the real fixed-query + Ollama + page-citation acceptance report `stage7-a3916b8ab2/report.json` is `ok: true`.

Remaining Stage 7 work: native macOS compilation/package fixes, real signing/notarization/update identities and the MacBook acceptance checklist. There is no Stage 8 in the current specification, so none was invented.

## 2026-09-01 — Windows sharing and remote API profile

- Prepared a clean Git/release path that excludes `.env`, SQLite/chat data, workspaces, installed skills, virtual environments, caches and release output while including the verified prebuilt frontend. Added a first-run friend launcher, Russian setup instructions and a deterministic Git-archive ZIP builder with SHA-256 output.
- The Windows first run checks Python, Docker, Ollama and free space, installs only missing project dependencies, builds the pinned sandbox runtime and offers to pull `qwen3.5:9b`. A recipient with the prebuilt frontend does not need Node.js or Git. Localhost-only binding and data-sharing warnings are explicit.
- Added `CONFIGURE_API.bat` for one optional remote OpenAI-compatible profile beside local Ollama, with presets for Z.AI/GLM and regional Qwen/DashScope endpoints plus a custom mode. The profile name appears in model selection. The key is read with hidden input into ignored local `.env`; the loader accepts only `SYMPHONY_*` assignments and never evaluates file contents. Sessions still persist only provider/model, never the key.
- The existing Gateway path supplies streaming text, compatible reasoning fields, usage and native tool calls. Provider/model selection and context stay scoped per chat. Multiple simultaneous remote endpoint profiles are intentionally not claimed; changing the one remote profile requires reconfiguration and restart.

Verification: all PowerShell scripts parse; 18 focused Gateway/chat/context tests pass. The final full backend run with `SYMPHONY_RUN_DOCKER_TESTS=1` reached **195 passed / 100%** on the real Docker runtime. Frontend **42/42 tests pass**; Windows hit an open-file limit with parallel icon transforms, so Vitest now uses one VM worker and completes reliably. TypeScript and Vite production build pass; the existing non-failing >500 KB main-chunk warning remains. Release-package inspection follows after the clean Git commit.

## 2026-09-02 — Turn completion recovery and permanent trash cleanup

- Fixed a real Ollama/Qwen failure observed in production history: a thinking-capable model could consume the entire 2,048-token generation budget with reasoning and return no visible answer or tool call. Symphony now records the condition and retries once with thinking disabled so the planned answer can be delivered instead of ending as `empty_response`.
- Provider timeouts and connection failures now produce actionable Ollama/OpenAI-compatible messages instead of blank transport errors.
- Added permanent chat deletion and bulk trash cleanup. Clearing trash removes the session, messages, turns, events, tool/approval records, attachments, artifacts, memory, research sources, FTS rows and the isolated on-disk session directory. The UI uses a separate irreversible-action confirmation and retains Restore for recoverable items.
- Focused backend regression suite: **10 passed**. Frontend: **42 passed**; TypeScript and production build successful. The existing non-failing bundle-size warning remains.
