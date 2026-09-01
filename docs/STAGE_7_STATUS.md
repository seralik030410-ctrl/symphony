# Stage 7 status — research and macOS packaging

Stage 7 is **in progress, not complete** (2026-09-01). Research/backend/frontend behavior has automated coverage; a live page read and citation were verified. Desktop source and a build pipeline are present, but native compilation, packaging and macOS acceptance have NOT run. There are remaining implementation items, not just acceptance paperwork.

## Implemented and verified on the current host

- `web.search` and `web.open` are registered tools in the existing bounded agent loop. Ordinary chat still goes directly to the selected model and does not enter a research or document router.
- Internet is disabled by default and configured per chat. Search always pauses for approval and exposes the exact sanitized query. Exact-domain allowlist entries can auto-allow page reads; an unknown domain receives a one-call approval only.
- The host network client accepts public HTTPS on port 443 only. It rejects credentials, probable secrets, local/special IPs, mixed public/private DNS answers, ambient proxies, cookies, compression, binary responses, oversized bodies and unsafe redirects. A verified public IP is pinned for each connection while TLS validates the original host.
- Search receives only bounded public keywords. Pages are untrusted evidence, never instructions. Search-result candidates are marked as unread until `web.open` verifies a page. Read sources persist per session/turn with URL, title, publication date when supplied, check time, hash and bounded excerpt.
- Research requests, responses and sources are durable events, restore after refresh and stay isolated between chats. The UI keeps sources in a collapsed disclosure rather than adding another dashboard.
- Settings now include a quiet **Internet** section and a privacy-minimal diagnostics report/ZIP. The ZIP contains package/migration/readiness metadata only—no chats, filenames, paths, environment variables, URLs, keys or raw logs.
- Settings → General includes a compact system/light/dark selector. System mode follows live OS changes and restores before React paints. Semantic light/dark tokens cover chat, settings, tool traces, workspace and artifact chrome; document pages/site previews preserve their own design. Palette tests enforce 4.5:1 for normal text, status, syntax and button pairs.
- Diagnostics includes a collapsed dependency setup path and a fixed `/api/setup/runtime-kit` download. Its ZIP has the matching Dockerfile/requirements, SHA-256 manifest, instructions and confirm-before-build Windows/macOS scripts. It needs Docker Desktop but no source checkout, Python, Node.js or Git. It never bundles keys, chats, paths or logs, and does not delete images, volumes, models or cache.

## Desktop candidate — implemented in source, NOT compiled/accepted

- Tauri 2 shell under `src-tauri` starts a loopback sidecar and keeps database/workspaces/skills in OS app data. Python readiness comes over the private parent pipe only after startup; a foreign process on 8765 cannot be mistaken for Symphony. Port binding occurs before database initialization. Parent EOF/shutdown stops the Python server; native shutdown has a bounded fallback for its own child only.
- Keychain/Credential Manager commands never return the saved value to JavaScript. Bootstrap sends the key through stdin, not command-line arguments or the environment. Key changes require restart. Native commands are restricted to the exact main-window URL; preview/file routes do not receive this capability.
- Native drops retain OS-selected file handles behind bounded, expiring, one-use tokens. Reads reject symlinks/unsupported types/oversized files and recheck size. Frontend batches survive attachment rerenders and stop at chat-switch boundaries. Python protocol and frontend batching are tested; Rust tests are written but not run.
- HTTPS system opener, updater plugin and update UI are wired. Installation checks active chats before installation/relaunch; do not start new turns from another browser during an update. There is no configured live update channel or signed package yet. Signature acceptance/rejection must still be tested on macOS.
- `scripts/build-sidecar.sh` freezes real frontend, migrations and trusted container-worker source into the sidecar and smoke-tests that executable. `scripts/build-macos.sh` requires real release configuration, signing and notarization credentials before bundling. The CLI version is locked by npm; binary icons are generated from the checked-in SVG. No release secrets or fabricated endpoint are committed.
- The macOS CI definition freezes a real sidecar, exercises its pipe lifecycle, then runs `cargo check`/`cargo test`. It has not been dispatched from this machine. There is no Cargo/Rust toolchain here.

## Verification on Windows

- Final backend with `SYMPHONY_RUN_DOCKER_TESTS=1`: **195 passed, no skips**, using actual Docker runtime 6.0. This supersedes the earlier 184-test run. The 11 new setup cases exercise the exact ZIP, missing/tampered resources, cancel/success/failure under real PowerShell, and real Bash/shasum inside the offline read-only runtime while mocking only the external Docker build call.
- Frontend: **42 passed**; TypeScript and Vite build passed. New cases cover OS/manual/cross-window theme state, blocked storage, first paint, semantic-token completeness and both palettes' contrast. Existing >500 KB JS chunk warning remains.
- Python sidecar: 11 cases cover bounded/malformed bootstrap, port ownership, readiness, command/EOF shutdown, no duplicate readiness and no key text in output.
- Live `qwen3.5:9b` used the actual `web.open` tool to read Python's asyncio documentation, returned a citation and check time, and persisted source/events. A new chat retained disabled networking and no sources. Evidence: ignored `data/acceptance/stage7-68f50f2ca9/report.json`.
- **Live search passed after moving to DuckDuckGo's lightweight HTML endpoint:** the fixed public query returned real candidate links, the separate page read/citation check passed through Ollama, and the isolated report is `data/acceptance/stage7-a3916b8ab2/report.json` with `ok: true`. Candidates remain unread until `web.open`; there is no silent second provider or CAPTCHA bypass.
- Isolated browser checks verified system/dark switching and chat, settings, workspace and PDF artifact surfaces at 1440/768/375 px without document horizontal overflow. PDF pages remained their intended light paper. Native desktop interactions are not browser-tested substitutes.
- Production backend was started on the free port 8765 and reports `0.7.0-dev`, stage `research`. Basic chat and host research also work when Docker is unavailable. Final browser check confirmed Internet settings/default-off controls and diagnostics; no console errors were observed.

## Remaining implementation/release work

1. Run the macOS pipeline, fix compile/package issues, lock verified Rust dependencies, and verify the bundled sidecar/runtime kit/worker resources from the installed app. The source review and Windows checks are not a native build.
2. Supply release identities/real updater channel, sign/notarize, then complete the following MacBook checks. These need a macOS host and the owner's release credentials; none were invented.

## macOS acceptance still required

Run this on the target Intel or Apple Silicon MacBook:

```bash
bash scripts/check-stage7-macos.sh
cp src-tauri/tauri.release.conf.example.json src-tauri/tauri.release.conf.json
# Fill the real HTTPS update endpoint and updater public key.
# Export TAURI_SIGNING_PRIVATE_KEY, APPLE_SIGNING_IDENTITY and notarization credentials.
bash scripts/build-macos.sh
```

Then verify all of the following before changing the stage to complete:

1. Install the signed DMG on a clean macOS user account and launch without a development checkout.
2. Create/reopen isolated chats, use Ollama local-first, quit/relaunch and confirm persistence.
3. Save/remove a test API key and verify it exists only in Keychain; restart and exercise the compatible provider.
4. Drop supported files into two different chats and confirm native attachment/isolation behavior.
5. Confirm a missing Ollama and missing Docker are explained by diagnostics; basic chat must not require Docker.
6. Exercise disabled internet, exact allowlist, one-call approval, redirect blocking, source dates/check time and refresh restoration.
7. Publish a separately signed test update, install it through Settings and confirm signature rejection for a modified package.
8. Check Gatekeeper signing/notarization on both the `.app` and `.dmg`.

## Current limitations

- DuckDuckGo Lite's result page is a deliberately small first search adapter and can change independently; provider failure stays explicit and page verification is always separate from search-result discovery.
- Publication dates are displayed only when the source page provides parseable metadata. Symphony never invents one.
- macOS signing, notarization, Keychain, native drop and updater behavior are candidates in source, **not compiled or runtime-verified on this Windows machine**.
- Docker Desktop initially failed before engine startup on its `dockerInference` temporary socket. Renaming that exact zero-byte socket failed with a Windows access error; no factory reset or volume/image deletion was performed. During the final check the engine became available again with runtime image 6.0; the full 184-test Docker run passed. The agent did not successfully repair or remove that socket. `START.bat` probes are now bounded so a stuck Docker pipe cannot hang ordinary-chat startup forever.
