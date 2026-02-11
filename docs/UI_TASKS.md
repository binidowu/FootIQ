# FootIQ UI Integration Tasks (MVP)

This document defines the frontend execution plan for integrating with the frozen backend contract (`API_CONTRACT.md` v1.1).

Status rule:
- Build in order.
- Do not bypass acceptance criteria.
- UI starts only after backend sign-off approval.

---

## 0) Scope & Constraints

- Backend entrypoint for UI: `POST /query` on Node gateway only.
- Contract source of truth: `docs/API_CONTRACT.md` (frozen).
- UI must not call Python service directly.
- Session continuity must be preserved via `session_id`.

---

## 1) Project Setup

### Tasks
- [x] Scaffold React + Vite app for FootIQ UI.
- [x] Add TypeScript support.
- [x] Add lint/format baseline.
- [x] Add env wiring for API base URL.

### Acceptance Criteria
- `npm run dev` starts successfully.
- Build succeeds with `npm run build`.
- API base URL can be configured without code edits.

---

## 2) Contract Types & API Client

### Tasks
- [x] Define strict request/response types from `API_CONTRACT.md`.
- [x] Build `query()` API client for Node `/query`.
- [x] Enforce runtime guards for required envelope fields.

### Acceptance Criteria
- UI rejects malformed API responses gracefully.
- `query()` always returns normalized shape to components.
- Errors include contract `error.code` and `error.message`.

---

## 3) Session Loop

### Tasks
- [x] Create `session_id` on first load and persist in browser storage.
- [x] Reuse same `session_id` for subsequent requests.
- [x] Reset session option (new session id) for demo control.

### Acceptance Criteria
- Sequential queries preserve context.
- Reset starts a clean conversation.

---

## 4) Chat UI

### Tasks
- [x] Build message list (user/assistant/error states).
- [x] Build composer with submit + loading state.
- [x] Disable double-submit while request is active.

### Acceptance Criteria
- User can send query, see pending state, receive response.
- Error responses render without breaking chat flow.

---

## 5) Markdown Renderer (Primary Answer Surface)

### Tasks
- [x] Render `output.answer` with `react-markdown` + `remark-gfm`.
- [x] Enable GitHub-flavored tables, lists, and links.
- [x] Sanitize markdown output (safe rendering policy).

### Acceptance Criteria
- Markdown tables render cleanly in answer panel.
- Unsafe HTML/scripts are not executed.
- Long answers remain readable on mobile and desktop.

---

## 6) Artifact Rendering

### Tasks
- [x] Build `ArtifactPanel` for structured artifacts in `output.artifacts`.
- [x] Render `plot`/`heatmap` URLs as images.
- [x] Render `stat_table` data as table component.
- [x] Detect image links inside markdown answer and surface inline or in panel.

### Render Precedence
1. `output.artifacts` (structured artifacts)
2. Image links found in markdown content
3. Markdown-only fallback

### Acceptance Criteria
- Plot URL `/static/plots/...` displays correctly.
- If structured artifacts are empty but markdown has image links, images still display.
- No duplicate rendering for same artifact URL.

---

## 7) Warnings, Errors, Suggestions

### Tasks
- [x] Render warnings as non-blocking chips/banners.
- [x] Render error block for `status:"error"` with code + message.
- [x] Render `suggestions` as quick-action buttons.
- [x] On suggestion click, auto-submit that text.

### Acceptance Criteria
- Warning codes are visible and readable.
- Error paths remain interactive (user can continue).
- Suggestion buttons are capped at 3 and actionable.

---

## 8) Debug Panel (Demo Critical)

### Tasks
- [x] Add collapsible debug panel per response.
- [x] Display:
  - `trace_id`
  - `metadata.data_depth` (`L1`/`L2`)
  - `metadata.reasoning_mode`
  - `metadata.tools_invoked`
  - response duration if available

### Acceptance Criteria
- Debug panel is hidden by default and easy to open.
- Data depth/reasoning/tool list visible for each assistant response.

---

## 9) UX States

### Tasks
- [x] Empty state with example prompts.
- [x] Loading skeleton/state while waiting.
- [x] Retry affordance for transient failures.
- [x] Mobile responsiveness pass.

### Acceptance Criteria
- Works smoothly at common mobile widths.
- No layout breakage with long markdown tables.

---

## 10) Integration Test Matrix (UI)

### Tasks
- [x] Mocked client tests for major contract scenarios.
- [ ] One manual end-to-end pass against local Node service.

### Required Scenario Coverage
- [x] `status:"ok"` surface response
- [x] `status:"ok"` deep response with artifact
- [x] `INSUFFICIENT_CONTEXT`
- [x] `PLAYER_NOT_FOUND`
- [x] `AMBIGUOUS_ENTITY`
- [x] `UPSTREAM_DOWN`
- [x] Replay warnings visible
- [x] Suggestions quick-send flow

### Acceptance Criteria
- Each scenario produces stable UI output.
- No uncaught exceptions in browser console.
Note: scenario stability is verified via `ui/src/test/App.integration.test.tsx` (7/7 passing). Browser-console check remains tied to manual E2E.

---

## 11) Documentation

### Tasks
- [ ] Add `README` section: run commands, env vars, API assumptions.
- [ ] Add known limitations list for MVP.
- [ ] Add screenshot/gif checklist for demo prep.

### Acceptance Criteria
- New team member can run UI in under 5 minutes.
- Demo handoff instructions are explicit.

---

## 12) UI Sign-Off Gate

- [ ] Contract compliance verified in UI.
- [ ] All required scenario checks passed.
- [ ] Artifact rendering validated in real flow.
- [ ] Debug panel validated in real flow.
- [ ] Product/demo owner approval recorded.

Approvers:
- Engineering: __________________
- Product/Demo Owner: __________________
- Date: __________________
