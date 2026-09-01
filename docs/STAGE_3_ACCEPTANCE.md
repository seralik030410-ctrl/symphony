# Stage 3 acceptance — 2026-08-30

## Scope and evidence

Stage 3 is the persistent code runtime: Python/Node image, per-chat project mount, shell/tests/build/preview, policy and approvals. Skills (Stage 4), document generators, research and multi-agent features are not implemented by this stage.

The earlier log entry marked Stage 3 complete with a scripted model and no running Docker daemon. This closeout adds real Docker and real Ollama verification; it does not reinterpret that earlier mock as a live run.

## Automated verification

```powershell
$env:SYMPHONY_RUN_DOCKER_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest --disable-warnings
cd frontend
npm test
npm run build
```

- Backend: **49 passed**, including six real-container tests. Last complete run: 38.64 seconds. Host Python 3.14 emits pytest-asyncio deprecation warnings (325); no test failures. Container Python is 3.12.
- Frontend: **17 passed**, covering event hydration, scroll follow intent, token summaries, scoped preview URLs, tab restore/deduplication/close, named Files tab and diff line numbering.
- TypeScript and Vite production build passed. Tests do not require model downloads or API keys. The live-model scenario below is deliberately separate.
- Added migrations 0005 (canonical permission profiles) and 0006 (recoverable chat trash). Migration DDL/version recording is transactional, with a rollback/retry regression test.

Real-container checks cover Python 3.12, Node 22, npm, pytest, office imports, git/ripgrep/curl/Poppler; non-root/read-only-root execution; absence of injected API keys and Docker socket; no-network default; output bounds; Stop and timeout killing children; orphan recovery scoped to this Symphony workspace; build/preview recovery after app restart.

Integration checks cover approval/denial/cancellation persistence, read-only write prompts, bounded model repair, source snapshot restore and budgets, chat deletion cancelling active turns, recovery of history/files, read-only source/diff APIs, binary/large/deleted files, and cross-chat/path traversal rejection.

## Real Ollama → project → Docker → preview

- Provider/model: local Ollama `qwen3.5:9b`.
- Context: **16,384** tokens, also confirmed in Ollama's loaded-model state. The 262,144 advertised model maximum is not the configured allocation.
- Session: `73d599e622184d3b8edd8b54e214f2e5`, titled **Проверка этапа 3 — сайт**.
- Turn: `62dd75c73c4e4841a395275e7ab2d65d`.
- Request: `Создай простой сайт кофейни «Утро»: заголовок, меню из трёх напитков, контакты и кнопка с работающим JavaScript. Собери проект, проверь тестом и покажи preview.`
- The model wrote `index.html`, `styles.css`, `app.js`, `package.json`, `build.js`, and `test.js`; no source project was prefilled by the harness.
- Nine successful calls: six file writes, two shell commands, one preview. Commands were `node test.js` and `node build.js`. These unknown script-entry commands required explicit one-time approvals; their complete script contents were reviewed before approving. The harness never automatically approves requests.
- Ten generated assertions passed in Docker; the build produced `dist/index.html`, `dist/styles.css`, and `dist/app.js`.
- HTML, CSS and JS all returned HTTP 200 from the session preview route. Completed turn duration was 238.344 seconds, including approval waits.
- Preview path: `/api/sessions/73d599e622184d3b8edd8b54e214f2e5/preview/dist/index.html`.
- Saved evidence: `data/acceptance/stage3-62dd75c73c4e4841a395275e7ab2d65d-verified.json` (ignored by Git, contains persisted public events).

Revalidate the saved run without another generation or command execution:

```powershell
.\.venv\Scripts\python.exe scripts/verify-live-stage3.py --verify-turn 62dd75c73c4e4841a395275e7ab2d65d
```

An earlier attempt timed out waiting for approval and used an echo-only build. It was cancelled, preserved as a failed report and is not counted as success. Build instructions were tightened to require real distribution assets. The successful run initially exposed a harness assumption: its test had already copied the HTML, so the build only changed CSS/JS. The verifier now requires real build-generated distribution changes plus valid HTML/assets instead of requiring that identical HTML be rewritten. The same saved run was rechecked; no generated source was patched to manufacture a pass.

## Browser and UI verification

- Production FastAPI UI at port **8765**, not the isolated UI fixture, displayed the real generated coffee site inside the docked workspace. Preview is no longer a modal. Code and Changes are separate tabs alongside Preview; + opens the chooser.
- Code is displayed as escaped React text with line numbers; Changes displayed all nine added source/distribution files from the saved first snapshot of that turn. Unified and two-column modes are available, with a snapshot selector.
- Reload restored Preview / app.js / Changes tabs and the active Changes selection. Another chat had zero messages and its own workspace state, not the previous chat's tabs/history.
- The user-reported Files button mismatch was fixed: it now opens a stable **Файлы проекта** tab, distinct from **Новая вкладка**. Opening a source preserves the files tab. Active tabs are revealed within the horizontally scrolling strip.
- Trash icons remain visible without hover. A synthetic QA chat was deleted through confirmation, disappeared from the list, survived a page reload in trash, then was restored through the UI. User chats were not deleted.
- 375px mobile: document width 375, composer bottom 812 at 812px viewport; history has a real scroll range (628px viewport, 2,130px content). Home moves to zero; PageDown and the return arrow work. The narrow-screen workspace fills the app area and can be hidden to return to chat.
- 1440px desktop with workspace: page width 1440, panel width ~691, chat scroll area ~619px high, composer bottom 900 at 900px viewport. The panel and conversation scroll independently; left rail and right inspector can be hidden.
- Security fixture: external JS module and button interaction passed; preview storage access failed with opaque-origin isolation, and fetch to the Symphony API was blocked by CSP. This synthetic security fixture is separate from the real generated-site acceptance.

## Explicit limits

- Preview is static HTML/CSS/JS from this chat, not a general browser or a persistent development server. Network, alerts/popups, forms and top-level navigation are blocked. The model-generated coffee button uses `alert`; its browser modal is intentionally blocked. Prefer DOM notifications in generated pages.
- Source views are read-only; edits/restores still use the audited tool/approval path. Diff compares current source with a snapshot, not Git branches. Snapshots exclude dependencies/VCS/cache directories.
- File view: 256 KB; tree: 500 entries; diff: 200 files / 500 KB. Snapshots: 50 MB / 5,000 files. Truncation/binary files are labelled, not silently presented as complete.
- Docker containment is a practical local development boundary, not a claim of protection against every kernel/daemon exploit. Unknown commands still prompt. Approved network grants container network access for that call, not a domain-level web policy.
- Single-user loopback API, no public authentication/multi-user isolation. Trash/snapshots retain disk space until a later retention feature. Research permissions and dependency-install lockfile workflows are not a full package-management system.
- The original rebuild specification's SHA-256 remains `EC12A8C63460D9C3F4D404BA2933C3213BA73D6039DB85426C8753D9C302DE79`, identical to the untouched legacy source.
