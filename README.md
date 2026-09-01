# Symphony 2.0

Stage 0–6 implementation plus Stage 7 work in progress from [docs/SYMPHONY_2_REBUILD_SPEC.md](docs/SYMPHONY_2_REBUILD_SPEC.md). Short Russian roadmap: [ЭТАПЫ_SYMPHONY.txt](ЭТАПЫ_SYMPHONY.txt). Stage 7 is NOT complete: native compilation and signed macOS acceptance remain; see [docs/STAGE_7_STATUS.md](docs/STAGE_7_STATUS.md).

The current release is a local-first direct chat runtime with observable workspace actions and isolated project execution. Chats remain strictly isolated. A model can work with files, run Python/Node commands in Docker, execute tests and builds, and expose a generated HTML preview. Every action and approval is persisted, streamed to the interface, and recoverable after refresh. Ordinary conversation still goes directly to the selected model and never passes through a document router.

## Implemented

- FastAPI backend with independent sessions, messages, turns, typed events, and audited tool calls.
- SQLite WAL storage, ordered SQL migrations, SSE replay, and restart recovery.
- One structured Model Gateway for Ollama and OpenAI-compatible APIs, including native tool calls.
- Bounded agent loop with a 12-call default limit, duplicate-call blocking, argument validation, timeout, Stop, failure observations, and model repair steps.
- Per-chat workspaces in `data/workspaces/{session_id}/worktree`; path traversal, drive paths, ADS, and workspace escapes are rejected.
- Registry: `fs.list`, `fs.read`, `fs.write`, `fs.apply_patch`, `search.rg`, `sandbox.shell`, `sandbox.preview`, `project.snapshots`, `project.restore`, `skill.read_resource`, `skill.run_script`, `artifact.schema`, `artifact.render`, `artifact.inspect`, `artifact.read_table`, `context.index_file`, `context.search`, and `vision.ocr`.
- Docker runtime based on Node 22 + Python 3.12, with pytest, git, ripgrep, curl, Poppler and office libraries. Non-root user, read-only root filesystem, dropped capabilities, process/CPU/memory limits, network off by default, and only the current chat worktree mounted read-write. There is deliberately no host-shell fallback.
- Four permission profiles: Read only, Project edit, Build (default), Full manual. Network/package installs and destructive shell commands need one-time approval; hard-denied host/device capabilities stay blocked in every profile.
- Recoverable source snapshots before mutating tools, streamed command output, bounded repair attempts, and Stop/timeout cleanup of the container process tree.
- React + TypeScript chat with custom accessible selectors, Markdown, refresh recovery, collapsible panels, inline tool traces, approval cards and Retry. Recoverable chat deletion uses a local trash, never permanent deletion.
- Right-hand workspace panel with Preview, source-code and Changes tabs, a new-tab chooser, file search, syntax colours, line numbers, copying, and unified/two-column diff. Tabs are persisted separately per chat. No preview modal covers the conversation.
- Provider-emitted reasoning, named stages and actual token usage. The configured 16,384-token window is sent to Ollama as `num_ctx`; the model's advertised maximum is not mistaken for the active allocation. Input totals across tool-loop steps are not context occupancy.
- Bottom-follow scrolling that respects manual history reading, a down-arrow return action when away from the bottom, and a keyboard-focusable conversation scroller. The composer stays visible while long history scrolls independently.
- Skills 2.0 metadata index with ZIP/local-folder/HTTPS-Git installation, including `repo.git#path/to/skill` for multi-skill repositories, Explicit/Auto/Always/Off modes, priority, editor/validation, deterministic test prompt, resource viewer, export, and recoverable trash. Oversized imported instructions are preserved verbatim as a progressively-read managed reference while the indexed `SKILL.md` stays prompt-safe.
- Skill scripts never run during installation. An activated script can run only through the registered `skill.run_script` tool, after approval, offline in Docker with the skill mounted read-only and only the current chat workspace writable. Skill selection/read/resource/script events are durable and visible inline.
- A full-screen settings surface keeps permissions, model selection, and Skills management out of the conversation chrome. The chat toolbar has one chat-panel toggle.
- Opt-in per-chat Internet research through `web.search` and `web.open`, with exact-query approval, exact-domain allowlists, public-HTTPS/SSRF defenses, durable network events and saved URL/publication/check dates. Search candidates are not presented as verified page sources until opened.
- Privacy-minimal diagnostics in Settings and as a downloadable ZIP. It reports runtime/dependency readiness without conversations, file paths, environment variables, source URLs, secrets or raw logs.
- System/light/dark application theme in **Settings → General**. The system choice follows OS changes without a reload; documents and sandboxed site previews retain their own colors.
- A standalone checked runtime kit under **Diagnostics → Dependency setup**. The ZIP contains the matching Docker recipe, SHA-256 manifest and confirm-before-build scripts for Windows/macOS; it requires Docker Desktop but no Symphony checkout, host Python, Node.js or Git.
- A Tauri 2 desktop candidate with loopback FastAPI sidecar, OS application-data storage, macOS Keychain/Windows Credential Manager integration, tokenized native file drop, HTTPS system opener and signed updater support. Real macOS acceptance remains mandatory.
- Automated coverage for direct chat, isolation, refresh, Stop, provider parity, workspace security, policy decisions, approval persistence, site build/preview, skills, trusted document generation, artifact integrity/versioning, and cross-chat isolation.

Stage 5 adds structured, versioned PDF/XLSX/DOCX/PPTX generation through trusted renderers. Stage 6 adds session-scoped file retrieval, semantic memory snapshots, compatible-model vision and local OCR. Stage 7 adds opt-in host-side research with saved sources and the Tauri macOS release candidate. There is no keyword-based document router or automatic file/research fallback for ordinary chat. See [Stage 6 acceptance](docs/STAGE_6_STATUS.md) and [Stage 7 acceptance status](docs/STAGE_7_STATUS.md).

## Context settings

Local Ollama and one remote OpenAI-compatible API can be available side by side. On Windows run `CONFIGURE_API.bat` for prepared Z.AI/GLM and Qwen/DashScope profiles or a custom endpoint, restart Symphony, then select it per chat under **Настройки → Общее → Модель**. The API key is written only to ignored local `.env`; see [API_PROVIDERS_RU.md](API_PROVIDERS_RU.md). Never commit or share that file.

Open a chat → **Настройки → Контекст и память → Лимиты модели**. Choose 8K / 16K / 32K / 64K and the maximum response length, then save. Both values are persisted per chat. Choices above the selected model's advertised limit are disabled; an unknown provider limit uses the conservative 16K fallback. Settings cannot change while a turn is active. A 64K choice is explicit and can need substantially more RAM/VRAM.

Ollama receives `num_ctx` and `num_predict`; compatible API requests receive `max_tokens`, with Symphony enforcing its own input budget. Changing Symphony's budget cannot enlarge a remote server's actual model window. Ollama model metadata is obtained from [`/api/show`](https://docs.ollama.com/api-reference/show-model-details), not guessed from the model name.

Automatic semantic compaction starts around 72% of the available input budget. The selected model summarizes older whole messages into Facts, Decisions, Open tasks and Artifact index through the same Gateway. At least the last ten messages stay verbatim; original history is never deleted. Snapshots retain source message IDs, versions and model usage. **Сжать сейчас** runs it manually; the collapsed editor supports corrections, clearing and version inspection. Model summaries can be imperfect: inspect important facts. Clearing creates an empty version; a later full window may trigger a new summary.

**Возможности выбранной модели** provides explicit vision/context-ceiling overrides for providers that do not advertise them. Overrides apply to that provider/model in every chat, not just the current session, and can be reset. Enabling a checkbox does not give a text-only model vision support.

The preflight budget includes instructions, schemas, unsummarized history, memory, retrieved excerpts, images, output and a tool-result reserve. Token counts before a response are estimates (roughly characters/3 plus message/image overhead); reported provider usage is shown separately. If whole recent messages still cannot fit, the turn fails with an actionable context-limit error rather than silently cutting the user's request. Compaction uses additional model calls and time; ordinary short chat does not.

After backend changes, restart the running Symphony backend and reload the browser. Rebuilding `frontend/dist` alone does not update an already-running Python process. `START.bat` starts dependencies but does not kill an existing backend or active turns.

## Sharing with a Windows friend

Use the release ZIP, extract it completely, install Python 3.12+, Docker Desktop and Ollama, then run `FRIEND_SETUP.bat`. It downloads `qwen3.5:9b` when missing, builds the matching runtime and starts the local app. Prebuilt `frontend/dist` means Node.js and Git are not required for the recipient. See `FRIEND_README_RU.txt`; never share your `data` directory.

## Requirements and setup

- Python 3.12+
- Node.js 20+ and npm
- Docker Desktop (Linux containers) for code execution, document generation, binary-document extraction, local OCR and preview builds
- Ollama, or an OpenAI-compatible server such as LM Studio, vLLM, or llama.cpp server

From PowerShell in the project root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\build-runtime.ps1
```

Defaults are documented in `.env.example`. Environment variables are read directly; `.env` is not automatically parsed.

```text
Ollama: http://127.0.0.1:11434, default model qwen3.5:9b
OpenAI-compatible: http://127.0.0.1:1234/v1, model local-model
Tool call limit: 12 per turn
Tool timeout: 10 seconds per call
Sandbox image: symphony-sandbox:stage3
Sandbox network: off unless policy and user approval allow it
```

If the configured Ollama default is missing, new chats select an installed local model (excluding `:cloud`). Models are not downloaded automatically. The live Stage 3 check used `qwen3.5:9b` at 16K context.

## Run

One-click Windows launch (starts Docker Desktop, builds the sandbox image when needed, starts Ollama and Symphony, then opens the browser):

```text
START.bat
```

The production frontend and API share [http://127.0.0.1:8765](http://127.0.0.1:8765). Development Vite remains available separately on port `5173`.

Production build:

```powershell
.\run.ps1
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765).

Development, in two terminals:

```powershell
.\scripts\run-backend.ps1
.\scripts\run-frontend.ps1
```

Vite runs at [http://127.0.0.1:5173](http://127.0.0.1:5173) and proxies `/api` to FastAPI.

### macOS release candidate

Desktop source is not yet natively compiled or packaged. On the target MacBook run `bash scripts/check-stage7-macos.sh`, configure `src-tauri/tauri.release.conf.json` with a real updater public key/HTTPS endpoint, export signing/notarization variables and run `bash scripts/build-macos.sh`. The build uses `.venv-desktop`, the npm-locked Tauri CLI and a real frozen-backend smoke test. Windows cannot validate Keychain/Gatekeeper/DMG. Complete remaining work and checklist: [docs/STAGE_7_STATUS.md](docs/STAGE_7_STATUS.md).

### Research preview

**Настройки → Интернет** enables networking for the current chat only. Search always asks you to review its exact outgoing query. Page reads can use explicitly allowed exact domains; unknown domains require a one-call approval. Search candidates are unread until opened. Saved sources show site-reported publication dates (or unknown) and the host's check time.

Live page reads, citations and candidate search worked with Ollama and DuckDuckGo Lite. Search still requires explicit review of the exact outgoing query; there is no hidden fallback to another provider. A candidate must be opened before it can support a claim. Reproduce the opt-in check with `python -m scripts.verify_live_stage7` (fixed public test data, separate ignored database, local Ollama).

If Docker Desktop fails (including the observed Windows `dockerInference` socket error), basic chat and host research still run; diagnostics explains sandbox availability. No factory reset is needed by Symphony, and the launcher does not delete Docker images/volumes. The engine was available again at the final Stage 7 check.

## Test and build

```powershell
.\scripts\test.ps1
```

Or individually:

```powershell
python -m pytest
cd frontend
npm test
npm run build
```

Run the opt-in real Docker checks from the project root after building the runtime image:

```powershell
$env:SYMPHONY_RUN_DOCKER_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest
```

Without that variable, real-container tests are skipped; the remaining tests still run. Live-model verification is separate and creates a labelled QA chat, without supplying prewritten project files:

```powershell
.\.venv\Scripts\python.exe scripts/verify-live-stage3.py
```

The helper does not approve commands for you. Review any pending approval in the UI. Reports go to ignored `data/acceptance/`. Recorded evidence and limitations are in [docs/STAGE_3_ACCEPTANCE.md](docs/STAGE_3_ACCEPTANCE.md).

## Architecture

```text
frontend/src/chat       messages, event reducer, public tool activity
frontend/src/activity   durable runtime event ledger
frontend/src/settings   provider and model selection
frontend/src/artifacts  docked document cards, page/table preview and versions
backend/skills          managed skill store, metadata index, matching and progressive reads
frontend/src/workspace  preview/code/diff tabs and read-only project inspection
backend/api             sessions, turns, retry, tools, tree, events
backend/agent           bounded context and structured tool loop
backend/artifacts       strict schemas, trusted renderers, runner and immutable store
backend/models          Gateway plus Ollama/OpenAI-compatible adapters
backend/research        bounded public HTTPS, parsers, per-chat source store
desktop                 private-pipe Python sidecar entrypoint
src-tauri               uncompiled desktop shell/release candidate
backend/tools           contracts, registry, secure workspace file tools
backend/sandbox         Docker runtime and command policy
backend/storage         repository, event store, ordered migrations
runtime-image           Node 22 + Python 3.12 + LibreOffice + Tesseract, label 6.0
tests/unit              storage, context, file security, timeout, policy
tests/integration       chat parity and Stage 2–7 contracts/acceptance scenarios
data/workspaces         isolated per-chat worktrees, ignored by Git
data/skills             managed installed skill copies, ignored by Git
```

Request path:

```text
session context -> selected model -> text and/or structured calls
                                  -> validated registry action
                                  -> policy / durable approval when required
                                  -> isolated Docker project command
                                  -> durable public events
                                  -> result returned to the same model
                                  -> final streamed answer
```

No document router, artifact fallback, or hidden action path is present. Skill matching is a small deterministic metadata matcher and is skipped entirely when no relevant/explicit skill exists.

## API

- `GET /api/health`
- `GET|POST /api/sessions`
- `GET|PATCH /api/sessions/{session_id}`
- `DELETE /api/sessions/{session_id}` (cancel active turn, move to trash)
- `GET /api/trash`
- `POST /api/sessions/{session_id}/restore`
- `GET /api/sessions/{session_id}/tree`
- `GET /api/sessions/{session_id}/files?path={relative_path}`
- `GET /api/sessions/{session_id}/changes?snapshot_id={optional_id}`
- `GET /api/sessions/{session_id}/snapshots`
- `GET /api/sessions/{session_id}/approvals`
- `GET /api/sessions/{session_id}/preview/{path}`
- `POST /api/sessions/{session_id}/turns`
- `GET /api/turns/{turn_id}`
- `POST /api/turns/{turn_id}/cancel`
- `POST /api/turns/{turn_id}/retry`
- `POST /api/approvals/{approval_id}/decision`
- `GET /api/turns/{turn_id}/events`
- `GET /api/turns/{turn_id}/events?stream=true&after={sequence}`
- `GET /api/models`
- `GET /api/tools`
- `GET /api/sandbox/health`
- `GET /api/skills` and `GET /api/skills/{skill_id}`
- `POST /api/skills/install`, `/api/skills/validate`, and `/api/skills/test`
- `PATCH|DELETE /api/skills/{skill_id}` and `POST /api/skills/{skill_id}/restore`
- `GET /api/skills/{skill_id}/resource` and `/api/skills/{skill_id}/export`
- `GET /api/sessions/{session_id}/artifacts` and artifact/version/file detail routes
- `GET|POST /api/sessions/{session_id}/inputs` (pending attachments/upload)
- `GET|DELETE /api/sessions/{session_id}/inputs/{attachment_id}` (scoped download/remove pending)
- `GET /api/sessions/{session_id}/sources?query={optional_query}`, `POST .../sources/index`, `DELETE .../sources?path={path}`
- `GET|PUT|DELETE /api/sessions/{session_id}/memory`, `POST .../memory/snapshot`, `GET .../memory/versions`
- `GET|PUT /api/sessions/{session_id}/model-capabilities`, `GET .../model-limits`
- `GET|PUT /api/sessions/{session_id}/research`, `GET .../research/sources?turn_id={optional_id}`
- `GET /api/diagnostics`, `GET /api/diagnostics/bundle` (privacy-minimal ZIP)

Every tool call has an audit id and durable status. SSE exposes the same saved records used by refresh recovery, including tool, file, approval, preview, model, and turn events.

Provider observability events include `model.reasoning_delta` and `model.usage`. Ollama usage comes from `prompt_eval_count` and `eval_count`; OpenAI-compatible streaming requests `stream_options.include_usage`. When a provider does not return usage, the UI explicitly shows that the value is unavailable.

Reasoning is a collapsed disclosure above the answer. Click it to read the provider's text; incoming fragments do not override your choice. The compact token line below an answer expands to show sent/received totals, reasoning tokens if reported, the latest call's input context, and the context-window limit. Totals cover all model calls in that turn; context occupancy is not their sum.

## Stage 5 documents

Ask for a PDF report, Excel workbook, Word document or PowerPoint presentation. The model calls `artifact.schema`, writes a JSON source with `fs.write`, then calls `artifact.render`. `artifact.inspect` lists prior versions and reads the saved source for revisions. The model does not need to write or execute renderer code. All these actions use the existing policy and tool loop.

- PDF: bounded `ReportSpec`, four visual presets, sections, tables, charts, callouts, embedded PNGs and citations. Unicode fonts, page numbers and actual rendered page images.
- XLSX: typed `WorkbookSpec` sheets/columns/rows, number formats and explicit formulas. Text that begins with `=` remains text. A bounded calculator verifies references, cycles and results for SUM/AVERAGE/MIN/MAX/COUNT/ABS/ROUND and arithmetic `+ - * /`. Unsupported formulas fail validation; external links/DDE/macros/network functions are not accepted. Excel recalculates when opened; preview uses the independently computed values, not invented cached values. [openpyxl does not calculate formulas](https://openpyxl.readthedocs.io/en/3.1.2/simple_formulae.html).
- DOCX: structured `DocumentSpec`, heading styles, tables, charts/images, headers/footers and sources. Preview is converted from the actual Word file with LibreOffice.
- PPTX: bounded `SlideSpec` for title/subtitle, bullets, tables, native charts, images and notes. Shape bounds and converted page count are checked; preview comes from the actual presentation.
- Renderer runs in a separate **offline** Docker container: one writable job directory, read-only trusted implementation, no project worktree/skills/host-home mount, non-root, no capabilities, CPU/RAM/PID limits, 150-second timeout. Stop removes its container process tree. No host-render fallback in production.
- Source JSON, recipe, result, validation/calculation report, page images and SHA-256 hashes are stored as immutable versions under `data/workspaces/{session_id}/artifacts`, outside the project sandbox mount. SQLite is the publication index. Failed/cancelled jobs never publish a successful artifact. Downloads recheck ownership and integrity. Trash preserves documents with their chat.
- The document card opens a docked tab; versions, pages, workbook sheets, download and source/recipe/check reports are available there. No document modal. **Файлы проекта** also lists the chat's documents.
- The composer paperclip imports documents up to 25 MB and images up to 10 MB into a unique `inputs/` filename (eight pending attachments). `artifact.read_table` reads bounded pages of CSV/XLSX (24 columns, up to 100 rows per call). Uploaded Excel formulas use cached values, explicitly labelled as possibly stale/absent. Stage 6 adds document indexing and image/OCR modes described below.

Limits: JSON source 4 MB; up to 80 PDF pages; workbook 10 sheets × 2,000 rows × 24 columns (preview first 200 rows); up to 30 slides; artifact bundle 100 MB. Automatic bounds checks are not a guarantee of perfect content, typography or absence of overlap; review the page preview. Artifacts/trash do not auto-expire. An OS crash during publication can leave an unindexed directory; it is never served and must not be treated as a completed document.

After upgrading, `START.bat` installs missing Python packages and rebuilds runtime label 6.0 once. First build downloads LibreOffice/fonts/Tesseract and may take several minutes. The image tag remains `symphony-sandbox:stage3` for compatibility; its label identifies the current runtime. Restart an already-running backend after upgrading. Preview uses PyMuPDF (AGPL/commercial licensing); review third-party distribution obligations before packaging a release.

Document API: `GET /api/sessions/{id}/artifacts`, `GET .../artifacts/{artifact_id}`, `GET .../artifacts/{artifact_id}/versions/{version}`, `GET .../versions/{version}/files/{filename}` and `POST /api/sessions/{id}/inputs`. Creation is a registered tool action, not an unapproved public render endpoint. Durable `artifact.validated` and `artifact.created` events feed refresh/SSE recovery.

Isolated visual fixture (temporary data, never the user's database): `python scripts/document-ui-fixture.py` on port **8767**. Its test-only local renderer creates actual PDF/XLSX; `--docker` verifies all four formats with the production document runner. It is not a production fallback. Production frontend/API remain on **8765**.

## Stage 6 files, images and verification

- Attach TXT/Markdown/CSV/JSON/PDF/DOCX/PPTX/XLSX; ask a question containing distinctive words from the source. SQLite FTS5 retrieves bounded fragments, not the entire large file. This is lexical search, not embedding-based semantic search. The inline source disclosure shows paths/chunks; **Настройки → Контекст и память → Индекс файлов** lists sources and lets you disconnect or reindex them.
- PDF/Office extraction runs fixed parsers in a separate offline, read-only, non-root Docker container with only a copied input and trusted worker mounted. There is no host fallback. Bounds include 25 MB input, 2 million extracted characters, 60 seconds, 512 MB RAM, PDF 1,000 pages, ZIP 5,000 entries / 80 MB expanded / 30 MB per entry; oversized or encrypted inputs fail explicitly. Image-only scanned PDF is not automatically OCRed; upload its page images.
- Image attachments accept PNG/JPEG/WebP, up to 10 MB / 40 million pixels each. **Изображения** selects compatible-model vision or local text OCR. Ollama capabilities come from `/api/show`; an unknown compatible API requires an explicit truthful override. OCR uses Tesseract in offline Docker and can feed a text-only model. It is text recognition, not general visual understanding. Images are sent only for the current turn, not silently repeated through future history.
- Pending attachments survive refresh and are excluded from retrieval before send. Sending is blocked while the UI upload batch is running. Sent attachments remain bound to immutable turns; Retry reuses the same files and image mode. SHA-256 checks reject changed attachments and stale indexed content. Disconnecting an index keeps the original file; deleting a pending upload removes that draft file.
- Memory, files, attachment use and source IDs remain scoped to the current chat. Source text is lower-priority untrusted evidence, never a system instruction or permission grant. Memory versions and source history currently have no automatic retention expiry.

Reproduce live Stage 6 acceptance with an installed vision model (default `qwen3.5:9b`) and built runtime:

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_live_stage6
```

This creates a separate ignored database/workspace under `data/acceptance/stage6-*`, not in user chats. It checks real DOCX extraction, OCR, Ollama vision, bounded document retrieval, semantic-memory provenance and ordinary-chat parity. The full Docker pytest run separately checks all four binary document formats. HTTP-mocked tests cover OpenAI-compatible payloads; no paid API live test is implied.

## Stage 4 acceptance check

Open **Настройки → Навыки**. The bundled `Static site quality` skill demonstrates the full flow. Use its Test prompt with `$static-site-quality проверь сайт`, or send a chat turn that explicitly asks it to read `references/checklist.md`. Confirm the inline trace shows selection, host-side `SKILL.md` read, the registered tool call, and the later resource read. Script calls always pause for approval and execute offline with the skill mounted read-only. Detailed evidence is in [docs/STAGE_4_ACCEPTANCE.md](docs/STAGE_4_ACCEPTANCE.md).

The supplied `skill_for_s` library was audited and imported as 31 unique Explicit skills; six byte-identical duplicate copies were intentionally collapsed. Folder, ZIP and HTTPS Git installation were each exercised through the production Settings UI. See [docs/SKILL_LIBRARY_AUDIT.md](docs/SKILL_LIBRARY_AUDIT.md).

### Workspace and chat controls

- Trash icons are always visible beside chats. Confirm deletion, then use **Отменить** or **Корзина → Восстановить**. Messages, events, source files and snapshots remain on disk; there is no permanent-purge feature yet.
- Top toolbar toggles the chat rail and event ledger. The code icon opens **Файлы проекта**; Preview opens the generated site in its own tab. The workspace's rightmost button hides it without closing tabs.
- **+** in the workspace opens a chooser for files, available builds and Changes. Close tabs with ×; arrow keys/Home/End navigate the tab bar. Drag the divider or use its arrow keys to resize. On narrow screens the panel occupies the app area; its hide button returns to the chat.
- File views are read-only. Change code through the chat tools; inspection does not bypass the approval system. Changes defaults to the snapshot before the latest turn that modified the project. Select another snapshot for a different baseline. This is a source comparison, not a Git branch/commit interface.
- Preview runs JavaScript in an opaque-origin sandbox. It cannot read Symphony storage or call its API. External network requests, browser alerts/popups, forms and top-level navigation are blocked. Use in-page UI for notifications. Static HTML/CSS/JS previews are supported; arbitrary localhost servers and external browsing are not.

### Permission and recovery details

| Profile | Automatic | Requires approval |
| --- | --- | --- |
| Read only | Project reads/search/preview | Every write and shell command |
| Project edit | Reads and snapshotted file edits | Shell commands and restores |
| Build (default) | Project edits; known offline `npm test`, `npm run build/test/lint/typecheck`, `pytest`, `node --test` commands | Unknown shell, installs, network, destructive commands, restore |
| Full manual | Read-only operations | Every write and shell command |

All profiles retain workspace isolation and hard capability denials. Even an allowed build can execute project code: command classification is not a shell security proof. Its containment is Docker plus a pre-command snapshot. Approval grants only that audited call. Operational session settings cannot change during a running turn. Host research uses separate per-chat opt-in/allowlist rules; emergency network disable remains available during a turn.

Snapshots are content-addressed outside the container mount. Source limits are 50 MB / 5,000 files; exceeding them prevents the mutation. Dependency/VCS caches (`node_modules`, `.venv`, `venv`, `.git`, `__pycache__`, `.pytest_cache`, `.npm`) are excluded. Ask the model to list or restore a snapshot; restore requires approval and first saves a safety snapshot. Snapshot history and trash do not currently expire automatically.

Inspection limits: 500 tree entries, 256 KB per text file, up to 200 changed files / 500 KB diff. Large and binary files are explicitly marked. This is a local single-user application, not an authenticated multi-user server: keep it on `127.0.0.1` and do not expose its API publicly.

### Isolated UI regression check

Build the frontend, then run `node scripts/ui-fixture.mjs` from the project root and open [UI fixture](http://127.0.0.1:8766). This serves the real production frontend with an in-memory test API: long history, empty chat, reasoning/text streaming, cancellation, and a simulated send error (`/error`). It never reads the user database or calls a real model. Restarting the fixture resets its test conversations. Production remains on port **8765**.

Check wheel/PageUp/PageDown scrolling, the down-arrow, a send while reading old history, expansion/collapse during streaming, refresh, and the composer at widths 375/768/1440 px. Frontend unit tests cover follow-mode transitions and usage aggregation. If Vite's config bundler is blocked by a restricted Windows environment, use `npm run build -- --configLoader runner` and `npm test -- --configLoader runner`.

## Stage 3 acceptance check

Ask the model: `Создай простой сайт, запусти тесты, собери его и покажи preview.` Confirm that:

1. Source files persist under only the active chat workspace.
2. Tests/build run in Docker and their stdout/stderr is visible in the tool trace.
3. Package installation or network access pauses for a one-time approval under the default policy.
4. Preview opens generated HTML in the right workspace panel; code and diffs open alongside it as tabs. Files from another chat cannot be read through the current chat's workspace routes.
5. Stop cancels the active turn/container, and refresh restores the complete action/approval trace.

The automated acceptance tests perform build, approval, preview, and isolation flows through the same Model Gateway and tool loop. If Docker is stopped or the image is missing, `/api/sandbox/health` and failed tool output report that state; commands are never executed on the host as a fallback.
