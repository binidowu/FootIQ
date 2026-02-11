# FootIQ

AI-powered football analytics assistant with a Node gateway, Python agent, and React UI.

## What It Does
FootIQ accepts natural-language football questions and returns:
- narrative answers,
- structured warnings/errors (contract-compliant),
- optional artifacts (plots/tables),
- debug metadata (trace ID, tools used, depth/mode).

Core wire contract: `docs/API_CONTRACT.md`.

## Architecture
```text
UI (:5173) -> Node Gateway (:3000) -> Python Agent (:8000)
                                        |- data_tools.py (SportsAPI + replay fixtures + cache)
                                        |- quant_tools.py (per90, derived metrics, z-scores, plots)
                                        |- football_agent.py (intent routing + tool loop)
```

Request lifecycle:
1. UI calls Node `POST /query`.
2. Node owns session, assigns `trace_id`, and forwards to Python `POST /agent/query`.
3. Python runs tools and returns a contract envelope (`status: "ok" | "error"`).
4. Node returns the envelope to UI unchanged (except gateway-level transport handling).

## Runtime Modes
- `live`: Python calls SportsAPI endpoints (plus cache).
- `replay`: Python uses local fixtures only (no network).

The UI toggle controls `constraints.data_mode` in each request.

## Prompt Matrix (What Works Today)
Use these prompts for reliable demos.

### Live mode (verified)
- `How is Haaland doing this season?`
- `How is De Bruyne doing this season?`
- `How is Bellingham doing this season?`
- `Compare Haaland and Mbappe`

### Replay mode (verified)
- `How is Haaland doing this season?`
- `Analyze Haaland xG trend`
- `How is Saka doing?`
- `Why is Haaland's output dropping?`

### Expected errors (and why)
- Unknown live players may return `UPSTREAM_DOWN` or `PLAYER_NOT_FOUND`.
- Replay queries without fixtures return contract errors by design.

## Warnings You Should Expect
- `SEARCH_UNAVAILABLE_USING_ALIAS` (live): `/search` endpoint unavailable on current plan; alias fallback used.
- `DATA_MODE_REPLAY` (replay): confirms replay/fixture path is active.
- `NORMALIZATION_GAP`: live stat type IDs encountered that are not mapped yet.

## Current MVP Limitations
1. Live search is effectively plan-gated in this setup.
  - Alias fallback currently supports: `Haaland`, `Bellingham`, `De Bruyne`, `Mbappe`.
2. Some live stat IDs are still unmapped and emit `NORMALIZATION_GAP`.
3. Replay supports only fixtures in `python_agent/tests/fixtures/sportapi/`.
4. Node session storage is in-memory only (no persistent DB).

## Setup
Prerequisites:
- Python 3.11+
- Node.js 18+
- Root `.env` with:
  - `OPENAI_API_KEY`
  - `SPORTAPI_KEY`
  - `SPORTAPI_BASE_URL`

Run services:
1. Python agent
```bash
cd python_agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

2. Node gateway
```bash
cd node_gateway
npm install
npm start
```

3. UI
```bash
cd ui
npm install
npm run dev
```

Open `http://localhost:5173`.

## Verification
- Python health: `curl -s http://127.0.0.1:8000/health`
- Node health: `curl -s http://127.0.0.1:3000/health`

Live smoke:
```bash
curl -s -X POST http://127.0.0.1:3000/query \
  -H "Content-Type: application/json" \
  -d '{"session_id":"smoke_live","query":"How is Haaland doing this season?","constraints":{"data_mode":"live","max_depth":"auto","allow_live_fetch":true}}'
```

Replay smoke:
```bash
curl -s -X POST http://127.0.0.1:3000/query \
  -H "Content-Type: application/json" \
  -d '{"session_id":"smoke_replay","query":"How is Haaland doing this season?","constraints":{"data_mode":"replay","max_depth":"auto","allow_live_fetch":true}}'
```

## Tests
- Python: `cd python_agent && source venv/bin/activate && pytest -q`
- UI: `cd ui && npm run test:run`
