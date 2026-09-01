# Symphony 2.0 Design Direction

## Scene

A person uses Symphony on a laptop through a long workday in mixed daylight, moving between short questions and sustained conversations; the screen must remain light, quiet, and legible without looking clinical.

## Register and system

Product register over a restrained, high-end neutral system. The layout follows one familiar product pattern: session rail, conversation canvas, event ledger. The left rail is required by the product specification, not decorative dashboard convention.

References and extracted moves:

- Linear: a second neutral layer separates navigation without heavy borders.
- Claude: generous reading measure and message hierarchy keep the answer primary.
- Arc: compact grouped navigation makes switching contexts feel immediate.

## Tokens

- Canvas: `#f3f5f7`
- Conversation surface: `#fafbfc`
- Raised surface: `#fdfefe`
- Primary ink: `#182027`
- Muted ink: `#68737d`
- Hairline: `#dfe4e8`
- Action accent: `#d95d39`
- Action hover: `#bd4d2d`
- Success: `#277a5a`
- Warning: `#9a650d`
- Error: `#b33d42`
- Focus: `#2f6f91`
- Type: system UI for labels and prose, system monospace for event metadata and code.
- Corners: 6px controls, 10px content surfaces. No oversized pills or nested cards.
- Motion: 150-200ms confirmation transitions, transform/opacity only, disabled under reduced motion.

Accent means action or active state only. Events use semantic colors, not decorative status dots. Empty, loading, error, streaming, cancelled, disabled, overflow, and mobile states all receive explicit treatment.

## Stage 4 turn trace

Tool activity belongs to the assistant turn that caused it. The default state is a compact expandable row with a tool title, registry name, textual status, and duration. Expanded content reveals arguments, result, changed files, and unified diff. Completion, failure, cancellation, and running states remain understandable without color. Retry appears only beside failed or cancelled assistant turns and creates a new immutable turn.

Each assistant turn owns one quiet status/disclosure above its answer, following the familiar chat pattern: `Думает…` while receiving reasoning, then a collapsed `Рассуждение` row. Provider reasoning uses normal readable prose with a single left hairline, not a nested scrolling code box. New deltas never reopen a disclosure. Token totals occupy a small expandable line below the answer; detailed context size, latest-input occupancy, and cumulative usage are revealed on demand. No stage chips, progress dashboards, or repeated completion badges.

An activated skill adds one collapsed inline disclosure, not another side panel. Its rows state the selected skill, host-side `SKILL.md` read, later resource reads, and approved script execution. The proof is derived only from durable events. Skill configuration lives in a full-screen Settings surface with a quiet left section rail, a compact metadata index, and one main editor; permissions also moved there to reduce chat-header clutter.

The app shell has an explicit viewport height and a bounded grid row. The conversation pane uses a flex column: header and composer do not shrink, and only the middle history viewport scrolls. Manual upward reading pauses follow mode, including during streaming. A centered circular down-arrow returns to the latest message. It is positioned inside the history viewport so it stays above a multiline composer. Expanded reasoning participates in the same history scroll, without a second vertical scrollbar.

## Workspace panel and navigation

The user's desktop reference establishes a docked workspace, not a preview modal. Chat remains on the left, with Preview, source files and Changes as tabs on the right. One tab is active; + opens a file/build chooser. The divider is resizable, panel visibility and per-chat tabs survive refresh, and narrow screens use a full-area panel with a return control. Source and diff views have independent bounded scrolling and never execute displayed code. Quiet syntax colours, line numbers and explicit +/− markers make changes readable without decorative cards.

The event ledger and workspace share the right-hand area rather than squeezing the chat between two inspectors. Trash icons remain visible, including on touch devices. Deletion uses a confirmation dialog, an undo notification, and a persistent recoverable trash. Dialogs are reserved for confirmation/trash, not work products. Primary icon targets are 44px with labels and focus rings.

## Stage 5 documents

Documents extend the existing workspace pattern: a compact file card in the assistant message opens a right-hand tab. The toolbar holds title, format/size, version selector and download; workbook sheet selection is contextual. Page images sit on a neutral inset canvas; tables have sticky headers and bounded overflow. Sources/recipe/validation are a disclosure below the result. No new dashboard, global panel or document modal was introduced.

Page and chat scrolling are independent. Document viewport supports wheel and keyboard navigation and preserves the visible composer. On mobile, the workspace uses the full app area with the existing return control. Generated source and cell values remain escaped text; PDF/office preview is rendered images, not executable document HTML.
## Stage 7 application themes

- `frontend/src/theme.css` is the semantic color layer. Light keeps the established neutral canvas; dark uses neutral elevations, off-white text and desaturated status colors without altering layout or interaction structure.
- The saved preference is `system`, `light` or `dark`; `system` follows `prefers-color-scheme` changes. A small head bootstrap applies the resolved scheme before React/styles to avoid a light flash.
- Chat, Settings, traces, workspace chrome and artifact controls use the semantic roles. Rendered document pages and sandboxed site previews are content surfaces and are deliberately not recolored.
- Automated palette checks require WCAG 4.5:1 for normal text/status/syntax/button pairs. Reduced-motion behavior remains governed by the existing media query.
