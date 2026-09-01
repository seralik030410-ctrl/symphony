# Stage 5 acceptance — trusted documents

Date: 2026-08-30. Source contract: `docs/SYMPHONY_2_REBUILD_SPEC.md`, Phase 5 and Artifact Engine sections.

## Result

Stage 5 is complete for the defined document scope. Requested PDF, XLSX, DOCX and PPTX files are generated from strict Pydantic data schemas by fixed trusted renderers. A model does not write or execute document renderer code. Ordinary chat remains on the direct Model Gateway path and produces no document/tool events unless a document or file action is requested.

## Implemented path

1. The same Ollama/OpenAI-compatible model loop calls `artifact.schema`.
2. The model writes a JSON source into only the active chat worktree with the existing `fs.write` tool.
3. `artifact.render` validates the source and starts a fixed offline Docker worker. The worker has one writable staging directory, a read-only mount of the trusted renderer implementation, no worktree mount, no network, no capabilities, non-root execution, resource limits and a 150-second timeout.
4. The renderer produces the native file. PDF is rasterized to page PNGs. DOCX/PPTX are reopened and converted from the actual native file to PDF with LibreOffice before page rasterization. XLSX is reopened and its expected formula cells/types are checked.
5. Validation output, dependency versions, source JSON, recipe, native result and SHA-256 file map are saved as an immutable artifact version. The SQLite row is published only in the final transaction. Cancelled/failed jobs clean their exact staging directory and emit no `artifact.created` event.
6. The event restores after refresh and displays a document card. The result opens in the existing docked workspace as page images or a bounded table preview; versions, sheets, downloads and source/recipe/validation reports are available there.

## Format validation

- PDF: Unicode fonts, headings/paragraphs/bullets, tables, bar/line charts, callouts, PNG images, citations and four presets. Actual pages are opened with PyMuPDF; page count and text bounds are checked; page images are the UI preview.
- XLSX: up to ten typed sheets, 24 columns and 2,000 rows per sheet. Header, widths, formats, freeze panes and filters are fixed renderer behavior. Explicit formula targets must be empty cells. A bounded AST interpreter supports `SUM`, `AVERAGE`, `MIN`, `MAX`, `COUNT`, `ABS`, `ROUND` and arithmetic; it detects invalid/out-of-data references, cycles, excessive ranges and non-finite results. External links, DDE, macros, remote functions and injected formulas are rejected. Text beginning with `=` stays text. openpyxl itself does not calculate formulas, so the preview uses Symphony's independently verified result and labels Excel recalculation honestly.
- DOCX: real styles, headings, tables, images/charts, header/footer and citations; the native output is reopened, then its rendered PDF is inspected.
- PPTX: fixed slide canvas and templates for bullets, table, native chart and PNG image; shape bounds and converted page count are checked. Notes are saved but not exposed in the visual preview.

Automatic validation proves structural and bounded geometry conditions, not perfect prose, typography or absence of all possible overlaps. The UI and README explicitly request human visual review.

## Isolation and integrity

- Artifact lookup and download always require the owning session ID. Replacing the URL's session ID returns 404.
- Managed artifacts live next to, not inside, the generated-code `worktree`; sandbox commands cannot modify them.
- Downloads compare the saved size and SHA-256 hash. A changed/missing file fails closed instead of being served.
- Artifact IDs cannot be adopted from another chat. A new version must match the original format and leaves older versions immutable.
- Input uploads use unique names below the active chat's `inputs/`; traversal, drive paths, macros and files above 8 MB are rejected. CSV/XLSX reads are paginated/bounded and never use another chat's path.
- Chat trash remains recoverable and retains managed documents. No permanent purge or automatic retention policy is claimed.

## Verification evidence

- Unit and integration coverage exercises strict schemas, unsafe/external/circular/out-of-data formulas, formula repair, real PDF/XLSX output, DOCX/PPTX reopen, events, persisted versions, integrity, cross-chat isolation, cancellation cleanup, input uploads, ordinary chat and Excel-attachment-to-PDF.
- Opt-in Docker coverage renders all four formats through the production worker. DOCX and PPTX are converted by LibreOffice, PDF pages are rasterized, and cancellation removes the real document container.
- Browser QA used an isolated data store. PDF pages and XLSX table/verified formula values open in docked tabs; saved versions switch correctly; DOCX/PPTX preview comes from the real Docker worker. Wheel and keyboard document scrolling work independently; page tabs restore after refresh; 375-pixel layout has no document overflow and the existing hide action returns to chat.
- Live Ollama acceptance uses `qwen3.5:9b` at the configured 16K context. It receives only the schema/tool path, writes structured sources, repairs reported validation errors, and must produce downloadable PDF and XLSX documents. Machine-readable evidence is ignored under `data/acceptance/stage5-live-<session>.json`; the final successful run is recorded below in `IMPLEMENTATION_LOG.md`.
- Final verification: 97 backend tests passed with real Docker coverage enabled; 20 frontend tests passed; TypeScript and the Vite production build completed successfully. The only frontend build note is Vite's non-failing chunk-size warning.

## Explicit non-goals

Stage 5 does not add keyword document routing, hidden fallback XLSX generation, model-generated host code, arbitrary formula execution, OCR, full-file retrieval, semantic memory, web research, publishing or macOS packaging. Those remain Phase 6/7 work.
