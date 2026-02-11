# FootIQ UI

AI-Powered Football Intelligence — Chat interface for the FootIQ analysis agent.

---

## Quick Start

### Prerequisites

| Dependency | Minimum Version |
|------------|----------------|
| Node.js    | 18+            |
| npm        | 9+             |

The FootIQ UI is one layer of a three-service stack:

```
┌──────────┐     ┌──────────────┐     ┌───────────────┐
│  UI      │────▶│ Node Gateway │────▶│ Python Agent   │
│ :5173    │     │ :3000        │     │ :8000          │
└──────────┘     └──────────────┘     └───────────────┘
```

### 1) Start the Python Agent

```bash
cd python_agent
source venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### 2) Start the Node Gateway

```bash
cd node_gateway
npm install   # first time only
npm start
```

### 3) Start the UI

```bash
cd ui
npm install   # first time only
npm run dev
```

Open **http://localhost:5173** in your browser.

---

## Environment Variables

| Variable | Location | Default | Description |
|----------|----------|---------|-------------|
| `VITE_API_BASE_URL` | `ui/.env` | `http://localhost:3000` | Node Gateway URL (Vite proxy target) |
| `OPENAI_API_KEY` | Root `.env` | — | Required by Python Agent for LLM calls |
| `OPENAI_MODEL` | Root `.env` | `gpt-4o-mini` | LLM model selection |

> **Note:** The UI never calls the Python agent directly. All traffic flows through the Node gateway at `/query`.

---

## Available Scripts

| Script | Description |
|--------|-------------|
| `npm run dev` | Start development server (port 5173) |
| `npm run build` | Production build to `dist/` |
| `npm run test` | Run integration tests (watch mode) |
| `npm run test:run` | Run integration tests (single run, CI-friendly) |

---

## Project Structure

```
ui/
├── src/
│   ├── api/
│   │   └── client.ts          # API client with runtime guards
│   ├── components/
│   │   ├── ArtifactPanel.tsx   # Plot images + stat tables
│   │   ├── ChatInput.tsx       # Auto-resize composer
│   │   ├── ChatMessageList.tsx # Scrollable message list
│   │   ├── DebugPanel.tsx      # Collapsible trace/tool metadata
│   │   ├── EmptyState.tsx      # Landing with example prompts
│   │   ├── MarkdownAnswer.tsx  # react-markdown + GFM tables
│   │   ├── MessageBubble.tsx   # Full message renderer
│   │   ├── SuggestionButtons.tsx # Quick-action buttons
│   │   └── WarningChips.tsx    # Non-blocking warning pills
│   ├── hooks/
│   │   └── useChat.ts          # Chat state management
│   ├── test/
│   │   ├── App.integration.test.tsx  # Integration test matrix
│   │   └── setup.ts            # Test environment setup
│   ├── types/
│   │   └── contract.ts         # TypeScript types from API_CONTRACT.md
│   ├── App.tsx                 # Main app shell
│   ├── index.css               # Design system (dark theme)
│   └── main.tsx                # Entry point
├── .env                        # Environment configuration
├── index.html                  # HTML entry with SEO meta
└── vite.config.ts              # Vite config with proxy
```

---

## Contract Compliance

The UI is built strictly against `docs/API_CONTRACT.md` (v1.1, frozen).

### Request
The UI sends to `POST /query`:
```json
{
  "session_id": "sess_...",
  "query": "How is Haaland doing this season?"
}
```

### Response handling
| Contract Field | UI Rendering |
|---------------|--------------|
| `output.answer` | Markdown with GFM tables, inline images |
| `output.artifacts` (plot/heatmap) | Image in artifact card |
| `output.artifacts` (stat_table) | Dynamic HTML table |
| `warnings[]` | Amber warning chips |
| `suggestions[]` | Blue click-to-send buttons (max 3) |
| `error.code` + `error.message` | Red error banner |
| `error.options[]` | Clickable entity suggestions |
| `metadata.data_depth` | L1/L2 badge in debug panel |
| `metadata.tools_invoked` | Tool chips with cache/duration |
| `trace_id` | Displayed in collapsible debug panel |

---

## Known Limitations (MVP)

1. **No streaming** — Responses appear all at once after the agent completes. A future WebSocket/SSE layer could enable token-by-token streaming.
2. **Single session per tab** — Session ID is generated per page load. Multiple tabs create separate sessions.
3. **Artifact generation is LLM-discretionary** — The agent decides whether to generate plots. Some L2 queries may return text-only responses without artifacts.
4. **No authentication** — MVP is for local demo use. Production deployment would require auth middleware.
5. **Session not persisted across refreshes** — In-memory only. Refreshing the page starts a new session.
6. **Replay mode not configurable from UI** — Currently defaults to `live` mode. Replay mode (`data_mode: "replay"`) can be set via direct API calls.

---

## Demo Preparation Checklist

- [ ] All three services running (Python :8000, Node :3000, UI :5173)
- [ ] `OPENAI_API_KEY` set in root `.env`
- [ ] Test with example queries from empty state
- [ ] Verify debug panel shows `trace_id`, `data_depth`, and `tools_invoked`
- [ ] Test error path by querying a misspelled player name
- [ ] Test "New Chat" button resets conversation
- [ ] Verify warning chips appear on cached data responses
- [ ] Verify suggestion buttons trigger new queries on click
- [ ] Check mobile layout at 375px width

---

## Integration Test Coverage

The integration test matrix (`src/test/App.integration.test.tsx`) covers:

| Scenario | Status |
|----------|--------|
| `status:"ok"` surface response | ✅ |
| `status:"ok"` deep response with artifact | ✅ |
| `INSUFFICIENT_CONTEXT` | ✅ |
| `PLAYER_NOT_FOUND` | ✅ |
| `AMBIGUOUS_ENTITY` | ✅ |
| `UPSTREAM_DOWN` | ✅ |
| Replay warnings visible | ✅ |
| Suggestions quick-send flow | ✅ |

Run: `npm run test:run` → 7/7 passing.
