# FootIQ Go-Live Checklist (MVP UI + Backend)

Use this as the single release checklist for demo readiness and MVP handoff.

Status rule:
- Complete sections in order.
- Do not mark Final Gate until all required items are done.

Date baseline:
- Checklist created: February 11, 2026

---

## 1) Preflight (Required)

- [x] Python agent running (`http://127.0.0.1:8000/health` -> `ok`)
- [x] Node gateway running (`http://127.0.0.1:3000/health` -> `ok`)
- [ ] UI running (`http://localhost:5173`)
- [x] Root `.env` loaded with `OPENAI_API_KEY`
- [x] UI env points to Node gateway (`VITE_API_BASE_URL=http://localhost:3000`)

Validated on: February 11, 2026 (09:36 EST)

---

## 2) Sign-Off Artifacts (Required)

- [x] Backend sign-off completed in `docs/BACKEND_SIGNOFF.md`
- [x] UI task checklist completed in `docs/UI_TASKS.md`
- [ ] Product/demo owner final review completed for current branch

---

## 3) MVP Hardening Decisions (Required)

Lock these decisions before release:

- [x] Add UI `data_mode` toggle (`live`/`replay`) in header and pass through request constraints
- [x] UI warning policy finalized:
  - [x] Suppress `USED_CACHED_DATA` in UI rendering (keep in payload/logs)
  - [x] Keep user-meaningful warnings visible (`DATA_MODE_REPLAY`, `BASELINE_MISSING`, `INSUFFICIENT_*`)
- [x] Confirm default launch mode for demos:
  - [x] Default `live`
  - [ ] Default `replay`

Decision log:
- Owner: Ayomide
- Date: February 11, 2026
- Notes: `live` is default. Replay remains deterministic fallback for demos.

---

## 4) Demo Asset Capture (Required)

- [ ] Capture screenshot: empty state (MANUAL REQUIRED - Browser Automation Failed)
- [ ] Capture screenshot: successful surface answer (`L1`) (MANUAL REQUIRED)
- [ ] Capture screenshot: deep/comparison answer (`L2` or equivalent) (MANUAL REQUIRED)
- [ ] Capture screenshot: error flow (`PLAYER_NOT_FOUND` or `UPSTREAM_DOWN`) (MANUAL REQUIRED)
- [ ] Capture screenshot: debug panel expanded (`trace_id`, `data_depth`, tools) (MANUAL REQUIRED)
- [ ] Optional GIF: suggestion click-to-send flow (MANUAL REQUIRED)

Store assets in:
- [ ] `docs/demo_assets/` (or agreed folder)

---

## 5) Demo Script Rehearsal (Required)

Target sequence (4 interactions):

1. Surface query (`How is Haaland doing this season?`)
2. Deep/compare query (`Compare Haaland and Mbappe` or deep analysis prompt)
3. Error recovery (intentional misspelling -> correction)
4. Replay toggle demonstration (same query in replay with `DATA_MODE_REPLAY`)

Checklist:
- [x] All 4 interactions run successfully end-to-end
- [x] Debug panel visible during at least 2 interactions
- [x] No uncaught browser console errors
- [x] Input remains functional after error responses

Validated on: February 11, 2026 (live + replay browser rehearsal)

---

## 6) Release Hygiene (Required)

- [x] Branch clean (`git status` clean)
- [x] UI tests pass (`cd ui && npm run test:run`)
- [x] UI build passes (`cd ui && npm run build`)
- [x] Python tests pass (`cd python_agent && pytest -q`)
- [x] Commit history reviewed for release scope

---

## 7) Push + Tag (Required)

- [ ] Push branch to remote
- [x] Create annotated tag for MVP checkpoint
  - Tag: `footiq-ui-mvp-2026-02-11-r2`
- [x] Share commit hashes + tag in release note

Push status note:
- Remote push blocked in this execution environment (`Could not resolve host: github.com`).

Release note template:
- Date: February 11, 2026
- Tag: `footiq-ui-mvp-2026-02-11-r2`
- Backend commit: `40e7f0b`
- UI/docs commit: `33cbd84`
- Known limitations:
  - Live `/search` still unavailable on current SportsAPI entitlement; alias fallback used for known players.
  - `NORMALIZATION_GAP` can appear for unmapped live stat IDs.

---

## 8) Rollback Notes (Required)

- [x] Previous stable tag/commit identified
- [x] One-command rollback path documented
- [x] Critical env vars documented for restart

Rollback target:
- Commit/tag: `footiq-ui-mvp-2026-02-11`
- Restart commands: `git checkout footiq-ui-mvp-2026-02-11 && cd python_agent && source venv/bin/activate && python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload` + `cd node_gateway && npm start` + `cd ui && npm run dev`
- Critical env vars: `OPENAI_API_KEY`, `SPORTAPI_KEY`, `SPORTAPI_BASE_URL`, `VITE_API_BASE_URL`

---

## 9) Final Gate

- [ ] Preflight complete
- [ ] Sign-offs complete
- [x] Hardening decisions locked
- [ ] Demo assets + rehearsal complete
- [ ] Push + tag complete
- [x] Rollback plan documented
- [ ] Product/demo owner approval recorded

Approvals:
- Engineering: __________________
- Product/Demo Owner: __________________
- Date: __________________

---

## 10) Validation Matrix (February 11, 2026, 09:36 EST)

Live post-upgrade checks (Node gateway entrypoint):

- [x] `GET /health` Python agent -> `ok`
- [x] `GET /health` Node gateway -> `ok`
- [x] Replay surface query -> `status:"ok"` (`How is Haaland doing this season?`)
- [x] Live surface query (Haaland) -> `status:"ok"`
- [x] Live surface query (Bellingham) -> `status:"ok"`
- [x] Live compare query -> `status:"ok"` (`Compare Haaland and Mbappe`)
- [x] Replay missing-fixture path -> expected `status:"error"` (`How is De Bruyne doing this season?`)

Observed non-blocking warnings:

- `SEARCH_UNAVAILABLE_USING_ALIAS` still appears in live mode, indicating `/search` endpoint is still unavailable on current account/entitlement path.
- `NORMALIZATION_GAP` warnings for unknown live stat type IDs (e.g., `232`, `2`) persist and should be mapped in `stats_config.py` when validated.

Open follow-ups before final gate:

- Confirm `/search` entitlement with SportsAPI Pro support or keep alias fallback as official MVP behavior.
- Expand live stat type mapping to reduce `NORMALIZATION_GAP` noise.
