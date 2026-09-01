# Supplied skill library audit

Audited on 2026-08-30 from `skill_for_s`. Installation itself did not execute any imported script, shell command, package manager, network instruction, hook, or model workflow.

## Result

- 37 `SKILL.md` files, 884 total files, 32.38 MB.
- 31 unique skills by SHA-256; six exact duplicate pairs were collapsed instead of installing duplicate slugs.
- All 31 unique skills installed successfully in **Explicit** mode. They activate only through `$slug` (or a deliberate mode change in Settings).
- 21 instruction documents exceeded the 8 KB prompt limit. Symphony kept each original verbatim in `references/symphony-full-skill.md` and installed a compact `SKILL.md` that requires `skill.read_resource` before use.
- 10 unique source skills include `.py`, `.js`, or `.sh` helpers. They are data at installation time. Symphony can execute only registered files below `scripts/`, only after approval, offline in Docker, with the installed skill read-only.
- No symlink or junction was accepted. Every installed tree stayed within the 1,000-file / 25 MB per-skill limits.

This is a structural and execution-surface audit, not a claim that every upstream workflow is appropriate for every task. In particular, `shannon` describes offensive security testing and should only be activated for an authorized target.

## Each installed skill

| Skill | Files | Prompt form | Executable helpers in source |
| --- | ---: | --- | --- |
| `shannon` | 6 | progressive | 2 |
| `code-reviewer` | 7 | direct | 3 |
| `claude-opus-4-5-migration` | 3 | direct | — |
| `frontend-design` | 1 | direct | — |
| `writing-hookify-rules` | 2 | progressive | — |
| `agent-development` | 8 | progressive | 1 |
| `command-development` | 12 | progressive | — |
| `hook-development` | 12 | progressive | 6 |
| `mcp-integration` | 8 | progressive | — |
| `plugin-settings` | 9 | progressive | 3 |
| `plugin-structure` | 8 | progressive | — |
| `skill-development` | 3 | progressive | — |
| `animate-expo` | 3 | progressive | — |
| `animate` | 3 | progressive | — |
| `animation-vocabulary` | 2 | progressive | — |
| `apple-design` | 2 | progressive | — |
| `ask-sonner` | 2 | direct | — |
| `emil-design-eng` | 2 | progressive | — |
| `find-animation-opportunities` | 2 | progressive | — |
| `improve-animations` | 3 | direct | — |
| `pick-ui-library` | 1 | direct | — |
| `prototype` | 2 | direct | — |
| `review-animations` | 3 | progressive | — |
| `write-swift` | 2 | progressive | — |
| `banner-design` | 3 | progressive | — |
| `brand` | 18 | direct | 1 |
| `design-system` | 27 | direct | 7 |
| `design` | 37 | progressive | 9 |
| `slides` | 6 | direct | — |
| `ui-styling` | 99 | progressive | 4 |
| `ui-ux-pro-max` | 71 | progressive | 15 |

## Exact duplicate copies not installed twice

Each pair below has the same SHA-256. The `.claude/skills` copy was installed and the `cli/assets/skills` packaging copy was skipped.

- `slides`
- `design-system`
- `brand`
- `banner-design`
- `design`
- `ui-styling`

## Installer verification

- **Folder:** production Settings dialog installed a local QA skill and displayed its metadata.
- **ZIP:** the same dialog uploaded a ZIP and preserved its nested `references/check.md` resource.
- **Git:** the dialog installed `https://github.com/anthropics/skills.git#skills/academy-guide`; its source was recorded as `git` and its resources were indexed. Sparse checkout keeps multi-skill repositories practical.
- All disposable QA skills were removed after verification. The active catalog contains the 31 skills above plus the bundled `static-site-quality` example.
