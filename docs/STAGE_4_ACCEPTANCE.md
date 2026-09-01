# Stage 4 acceptance — Skills 2.0

Verified on 2026-08-30 against the production app at `127.0.0.1:8765`.

## Implemented contract

- SQLite migration `0007_skills.sql` stores only indexed metadata and lifecycle state. Installed files live in the managed `data/skills/{skill_id}` tree.
- ZIP, local folder, and HTTPS Git sources are supported. Git fragments select one skill from a multi-skill repository (`repo.git#path/to/skill`) and use sparse checkout. Limits, traversal, symlink/junction, credential-bearing Git URL, archive bomb, duplicate slug and invalid manifest checks fail closed. Long imported instructions are preserved verbatim as a managed progressive reference while direct editor input remains limited to 8 KB.
- Activation modes are Off, Explicit, Auto, and Always. Deterministic metadata matching is available without a model through the Test prompt UI/API.
- A normal unrelated chat emits no skill events and receives no skill prompt suffix. On activation, the host reads full `SKILL.md`; linked resources are read only through `skill.read_resource`.
- `skill.run_script` accepts only `.py`, `.js`, or `.sh` below `scripts/`. It always requires approval, runs offline in Docker, mounts the skill read-only, and writes only to the current chat workspace.
- Settings contains install, enable/mode, priority, edit/validate, resource read, dependencies, test prompt, export, recoverable delete, and restore controls.

## Automated evidence

- Backend default suite: **53 passed, 7 skipped**. It covers store lifecycle, matching, progressive disclosure, safe ZIP import/export, long-import normalization, Git subdirectory/sparse checkout, Windows read-only Git cleanup, folded YAML descriptions, edit rollback on slug conflict, API flow, event order, and approval gating.
- Frontend: **17 passed** and the TypeScript/Vite production build succeeds.
- Real Docker suite: **7 passed** with `SYMPHONY_RUN_DOCKER_TESTS=1`. The Stage 4 case proved the skill mount rejects mutation, network is off, and only `skill-output.txt` in the active workspace changes.

## Supplied library and installer UI evidence

- Scanned **37** `SKILL.md` files and **884** files (32.38 MB) under `skill_for_s`; SHA-256 grouping found **31 unique skills** and six byte-identical duplicate pairs.
- Installed all 31 unique skills in Explicit mode. **21** long instruction documents were converted to prompt-safe progressive form without losing their original text; **10** source skills contain executable helper files, but none were run during audit or installation.
- Loaded every installed detail through the production API, read every normalized full-instruction resource, and verified `$slug` deterministic activation for all 32 active entries (31 imported plus the bundled example): **0 failures**.
- Production Settings UI successfully installed disposable QA skills from a local folder and ZIP, including a nested resource. HTTPS Git successfully installed the official Anthropic `academy-guide` subdirectory using `https://github.com/anthropics/skills.git#skills/academy-guide`. QA entries and files were purged afterward; the active library returned to 32 entries.
- The first live Git attempt exposed two Windows-specific defects: read-only `.git` pack cleanup and an inefficient full-repository clone. Both were fixed with forced read-only cleanup and sparse checkout, covered by regression tests, and the same UI operation then passed.

## Live Ollama evidence

QA session `aee79398f3ee4049a69774243b370b9f`, turn `86e584ee0c424ec9829c58971fde92ca`, model `qwen3.5:9b` completed successfully. Its durable event order included:

```text
skill.cataloged
skill.selected
skill.read (SKILL.md)
model.started
tool.requested (skill.read_resource)
tool.started
tool.output
skill.resource_read (references/checklist.md)
tool.completed
model.started
turn.completed
```

The reference text was absent from the initial prompt and appeared only in the tool result passed to the second model step. The live UI showed the same selection/read/resource proof in a collapsed inline trace, with no console errors.

## Responsive UI evidence

The full-screen Settings and Skills manager were inspected at the normal desktop viewport and at 375×812. The 375 px document had `scrollWidth === innerWidth`; navigation, skill index, editor controls, resources, and activation settings remained reachable. The conversation toolbar now exposes one chat-rail toggle; project-workspace hiding remains a separate control for the separate right panel.
