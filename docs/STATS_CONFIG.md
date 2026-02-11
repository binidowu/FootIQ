# FootIQ Statistics Configuration (STATS_CONFIG)

This document defines the **metric registry** — the data contract between raw SportsAPIPro responses and the FootIQ agent's quantitative tools.

Every metric the system can reason about must be declared here. If it's not in this table, the agent cannot use it.

---

## 1) Design Decisions

### Why a Static Metric Map?

SportsAPIPro returns statistics as arrays of `{type: <int>, value: <num>}`. Without a registry, the agent would need to guess what each `type` means at runtime. This map provides:

- **Human-readable names** for LLM prompts and UI
- **Type safety** (int vs float vs percentage)
- **Missing-data policy** (is `null` truly missing, or is it a valid zero?)
- **Aggregation rules** (how to combine across multiple games)

### Two-Tier Availability Model

| Tier | Source | Latency | Completeness |
|------|--------|---------|--------------|
| **L1** | `get_athlete_games` (summary stats) | ~100ms | Always available |
| **L2** | `get_game_lineup` (detailed per-game) | ~200ms per game | Depends on league/provider |

The agent decides which tier to query based on the user's question and `constraints.max_depth`.

---

## 2) Core Metrics (L1 — Always Available)

These are returned in every `get_athlete_games` response.

| API Type ID | Metric Key | Display Name | Data Type | Unit | Missing Semantics | Per-90 Rule | Notes |
|-------------|-----------|--------------|-----------|------|-------------------|-------------|-------|
| 10 | `rating` | Match Rating | float | 0–10 scale | `missing` | N/A (already per-game) | SofaScore-style composite |
| 27 | `goals` | Goals | int | count | `true_zero` | `per90_by_minutes` | Outfield only |
| 26 | `assists` | Assists | int | count | `true_zero` | `per90_by_minutes` | |
| 30 | `minutes_played` | Minutes Played | int | minutes | `true_zero` | N/A (denominator) | Used as denominator for per-90 |
| 14 | `yellow_cards` | Yellow Cards | int | count | `true_zero` | `per90_by_minutes` | |
| 15 | `red_cards` | Red Cards | int | count | `true_zero` | `per90_by_minutes` | |

---

## 3) Advanced Metrics (L2 — Detailed Lineups Only)

These require fetching individual game lineups. May be unavailable for some leagues/games.

| API Type ID | Metric Key | Display Name | Data Type | Unit | Missing Semantics | Per-90 Rule | Notes |
|-------------|-----------|--------------|-----------|------|-------------------|-------------|-------|
| 76 | `expected_goals` | Expected Goals (xG) | float | xG | `missing` | `per90_by_minutes` | Opta-sourced; not available in all leagues |
| 3 | `shots_total` | Total Shots | int | count | `missing` | `per90_by_minutes` | Denominator for accuracy |
| 4 | `shots_on_target` | Shots on Target | int | count | `missing` | `per90_by_minutes` | Numerator for accuracy |
| 55 | `touches_in_box` | Touches in Penalty Box | int | count | `missing` | `per90_by_minutes` | Positional involvement |
| 46 | `key_passes` | Key Passes | int | count | `missing` | `per90_by_minutes` | Chance creation |
| 78 | `tackles_won` | Tackles Won | int | count | `missing` | `per90_by_minutes` | Defensive metric |

### 3.1 Observed Internal IDs (Not User-Facing Metrics)

These IDs have appeared in live responses and are tracked internally to reduce warning noise.
They are not currently surfaced as user-facing analytics metrics.

| API Type ID | Internal Key | Handling |
|-------------|--------------|----------|
| 2 | `unknown_2` | Stored internally, excluded from analytics output |
| 232 | `unknown_232` | Stored internally, excluded from analytics output |

---

## 4) Derived Metrics (Computed by FootIQ)

These are **not** fetched from the API. They are calculated from raw metrics.

| Metric Key | Display Name | Formula | Required Inputs | Notes |
|-----------|--------------|---------|-----------------|-------|
| `shot_accuracy` | Shot Accuracy | `sum(shots_on_target) / sum(shots_total)` | `shots_on_target`, `shots_total` | Weighted ratio across games; **not** averaged per-game |
| `goal_involvement` | Goal Involvement | `goals + assists` | `goals`, `assists` | Simple additive |
| `xg_overperformance` | xG Overperformance | `goals - expected_goals` | `goals`, `expected_goals` | Positive = finishing above expectation |
| `minutes_per_goal` | Minutes per Goal | `sum(minutes) / sum(goals)` | `minutes_played`, `goals` | Returns `null` if `goals == 0` |

---

## 5) Missing Data Semantics

### 5.1 Two Semantic Categories

| Semantics | Meaning | Example | Agent Behavior |
|-----------|---------|---------|----------------|
| `true_zero` | The event genuinely didn't happen | Goals = 0 → player scored 0 | Treat as `0` |
| `missing` | Data was not collected/available | xG = null → Opta feed missing | Treat as `null`; do NOT impute to 0 |

> [!CAUTION]
> Treating `missing` xG as `0.0` would make a player appear to massively overperform. Always check `missing_semantics` before aggregation.

### 5.2 Field Presence Rules

API responses may express "no data" in two ways. The agent MUST handle both consistently:

| Scenario | Payload Shape | Interpretation for `true_zero` | Interpretation for `missing` |
|----------|--------------|-------------------------------|------------------------------|
| Field present, value is `null` | `{"type": 27, "value": null}` | Treat as `0` | Treat as `null` (data unavailable) |
| Field absent from array | `statistics: [...]` with no entry for type 27 | Treat as `0` | Treat as `null` (data unavailable) |
| Field present, value is `0` | `{"type": 27, "value": 0}` | Treat as `0` | Treat as `0` (explicitly zero) |

**Implementation rule:** When extracting a metric from the statistics array:
1. Search for the `type` ID.
2. If not found AND `missing_semantics == "true_zero"` → use `0`.
3. If not found AND `missing_semantics == "missing"` → use `null`.
4. If found with `value: null` → apply same logic as "not found" above.
5. If found with a numeric value → use as-is.

---

## 6) Per-90 Normalization Rules

### `per90_by_minutes` (for count metrics)

```
per_90 = (sum(metric_across_games) / sum(minutes_across_games)) * 90
```

**Why sum/sum, not average of per-game rates?**
Averaging per-game rates biases toward low-minute games. A player who plays 10 minutes and scores 1 goal would show 9.0 goals/90 for that game, skewing the average.

**Minimum minutes threshold:** Player must have ≥ 90 total minutes across the window. If below threshold:
- Return `null` for per-90 value.
- Emit warning: `INSUFFICIENT_MINUTES` with `details: {"total_minutes": <N>, "threshold": 90}`.

### `weighted_ratio` (for percentage metrics)

```
shot_accuracy = sum(numerator) / sum(denominator)
```

If denominator is 0, return `null` (not 0%).

### N/A

Metrics like `rating` (already normalized per-game) or `minutes_played` (the denominator itself) don't get per-90 treatment.

---

## 7) Unresolved Metric ID Handling (Runtime Safety)

> [!IMPORTANT]
> API Type IDs in this document are **provisional**. They MUST be validated against actual SportsAPIPro responses during implementation.

**Runtime rule:** If the agent encounters a statistic `type` ID that is NOT in this registry:

1. **Skip** the metric entirely — do NOT attempt to interpret it.
2. Emit warning: `NORMALIZATION_GAP` with `details: {"unknown_type_id": <N>, "source": "<endpoint>"}`.
3. **Continue** processing the response — this is a non-fatal condition.
4. Log the unknown ID for later addition to this registry.

**Validation approach at implementation time:**
1. Fetch a known player's game data (e.g., Haaland).
2. Log the raw `statistics` array.
3. Map each `type` ID to its meaning by cross-referencing with known values.
4. Update this table with confirmed IDs.

---

## 8) Aggregation Windows

When the agent aggregates stats across multiple games:

| Window | Description | Typical Use |
|--------|-------------|-------------|
| `last_N` | Last N games played | "How has he done in his last 5?" |
| `season` | Current season to date | "How's his season going?" |
| `date_range` | Between two dates | "Form since January" |

**Default:** `last_5` if user doesn't specify.

---

## 9) Z-Score Baseline Schema

File: `python_agent/config/baselines.json`

### 9.1 Dimensions

| Dimension | Example Values |
|-----------|---------------|
| `league` | `"premier_league"`, `"la_liga"`, `"bundesliga"` |
| `season` | `"2025_2026"` |
| `position_group` | `"all_positions"` (MVP), later: `"forward"`, `"midfielder"`, `"defender"` |

### 9.2 Schema

```json
{
  "premier_league": {
    "2025_2026": {
      "all_positions": {
        "rating": {"mean": 6.85, "std": 0.55, "n": 200},
        "goals": {"mean": 0.25, "std": 0.22, "n": 200},
        "expected_goals": {"mean": 0.28, "std": 0.20, "n": 150}
      }
    }
  }
}
```

`n` = sample size. Used for confidence gating (see guardrails below).

### 9.3 Z-Score Guardrails

| Condition | Behavior | Warning |
|-----------|----------|---------|
| Baseline missing for league/season/position | Disable z-score for that metric | `BASELINE_MISSING` with `details.fallback: "raw_per90"` |
| `std == 0` | Disable z-score (division by zero) | `BASELINE_MISSING` with `details.fallback: "raw_per90", details.reason: "zero_variance"` |
| `n < 30` | Disable z-score (insufficient sample) | `BASELINE_MISSING` with `details.fallback: "raw_per90", details.reason: "low_sample", details.n: <N>` |

In all fallback cases: return the **raw per-90 value** without z-score interpretation. The agent should narrate "compared to league average" only when z-score is available.

> [!NOTE]
> Self-baseline (player vs their own history) is a future enhancement. MVP uses league-level baselines only.

---

## 10) Position Groups

For baseline comparisons and metric relevance:

| Group | Positions Included | Key Metrics |
|-------|-------------------|-------------|
| `forward` | ST, CF, LW, RW | goals, xG, shots, touches_in_box |
| `midfielder` | CM, CAM, CDM, LM, RM | key_passes, assists, tackles_won |
| `defender` | CB, LB, RB, LWB, RWB | tackles_won, rating |
| `goalkeeper` | GK | *Out of scope for MVP* |

> [!IMPORTANT]
> MVP uses `"all_positions"` for baselines. Position-specific baselines are a post-MVP enhancement. The position group mapping is defined here for forward compatibility.

---

## 11) Example: Full Normalization Flow

**Query:** "How is Haaland doing per 90 this season?"

1. Fetch last 5 games via `get_athlete_games` → L1 data.
2. Extract `goals`, `assists`, `minutes_played` (all L1, `true_zero` semantics).
3. For each metric, apply field presence rules (Section 5.2).
4. Aggregate: `sum(goals)=4`, `sum(minutes)=420`.
5. Check minutes threshold: `420 >= 90` → proceed.
6. Per-90: `(4/420)*90 = 0.857 goals/90`.
7. Z-score: baseline `goals.mean=0.25, goals.std=0.22, n=200`.
8. Check guardrails: `std > 0`, `n >= 30` → proceed.
9. Z = `(0.857 - 0.25) / 0.22 = 2.76` → "Exceptional" (>2σ above mean).
10. Return in natural language with the raw value and context.
