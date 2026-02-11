# Intent Routing & Tool Selection (Phase 4)

This document defines the deterministic rules for mapping user queries to tool chains.
The router runs *before* the LLM agent to enforce constraints and select the optimal toolset.

## 1. Intent Tiers

| Intent | Triggers (Regex/Keyword) | Allowed Tools | Data Depth |
|--------|-------------------------|---------------|------------|
| **Surface** | `how is (?:he|she|they|X) doing`, `(.*) stats`, `(.*) form`, `support`, `help` | `search_player`, `get_recent_games`, `calculate_per90`, `compare_to_league` | L1 |
| **Deep** | `why`, `analyze`, `decline`, `improve`, `xG`, `shot`, `heatmap`, `tactical` | *All Surface Tools* + `get_detailed_stats`, `calculate_derived`, `show_form_chart` | L2 |
| **Compare** | `compare`, `vs`, `better than` | `search_player`, `get_recent_games`, `calculate_per90` | L1 |

## 2. Hard Constraints

### Max Depth Constraint
If request `max_depth="L1"`:
- **Deep** intent is downgraded to **Surface**.
- `get_detailed_stats` (Lineup tool) is physically excluded.
- `calculate_derived` and `show_form_chart` are physically excluded.

### Data Mode Constraint
If request `data_mode="replay"`:
- All tools must operate in replay mode (no external API calls).
- `search_player` must return static fixtures.

## 3. Fallback & Error Rules

| Condition | Outcome | Contract Error Code |
|-----------|---------|---------------------|
| Cold start + pronouns ("how is *he* doing") | Abort immediately | `INSUFFICIENT_CONTEXT` |
| `search_player` returns 0 results | Abort immediately | `PLAYER_NOT_FOUND` |
| `search_player` returns >1 high-conf result | Abort immediately | `AMBIGUOUS_ENTITY` |
| `get_recent_games` returns 0 games | Abort immediately | `INSUFFICIENT_DATA` |
| `get_recent_games` returns 1-2 games | Continue + Warning | `INSUFFICIENT_GAMES` (Warning) |

## 4. LLM System Prompt Strategy

The system prompt will be dynamically constructed based on the selected intent:

- **Surface**: "You are a football analyst. Focus on high-level goal/assist output and basic form ratings. Do not speculate on tactics."
- **Deep**: "You are a tactical expert. Use lineup data, xG, and derived metrics to explain performance trends. Generate plots for key metrics."
- **Compare**: "You are a scout. Compare players head-to-head on per-90 metrics. Be objective."

## 5. Runtime Prerequisite

- `OPENAI_API_KEY` must be set for live LLM execution.
- If it is missing, the agent MUST return contract error code `UPSTREAM_DOWN`.
