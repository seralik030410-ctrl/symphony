---
name: Static site quality
description: Build or review dependency-free HTML, CSS and JavaScript sites and веб-сайты with accessibility, responsive layout, tests and a real dist preview; создать, исправить или проверить сайт и веб-страницу.
---

# Static site quality

Use this workflow when the user asks to create, repair, or review a simple static website.

1. Inspect the existing project before changing it.
2. Keep the source dependency-free unless the user requests a framework.
3. Preserve semantic HTML, keyboard access, visible focus, and responsive behavior.
4. Add real tests for required content and behavior.
5. Run the tests and a real build that creates `dist/index.html` with its local assets.
6. Open `dist/index.html` through the preview tool and report only verified results.

For the detailed acceptance checklist, read `references/checklist.md` with `skill.read_resource`.
The optional `scripts/check_site.py` performs an offline structural check. Read it first, then run it only through `skill.run_script`; never bypass the approval shown by Symphony.
