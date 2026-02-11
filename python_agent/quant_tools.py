"""
FootIQ Quantitative Tools — Per-90, Derived Metrics, Z-Score, Form, Plots

Transforms normalized game data (from data_tools.py) into analytical outputs.
All rules follow STATS_CONFIG.md §4, §6, §9.

Adjustments applied:
- metric_key in compute_zscore signature
- matplotlib Agg backend (headless-safe)
- METRIC_UNAVAILABLE for missing derived inputs
- Contract-compliant plot naming: {trace_id}_form-{metric_key}.png
- ARTIFACT_WRITE_FAILED on plot I/O errors
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Force non-GUI matplotlib backend before any pyplot import
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from stats_config import (
    KEY_TO_METRIC, Per90Rule, MissingSemantic,
    SHOT_ACCURACY, GOAL_INVOLVEMENT, XG_OVERPERFORMANCE, MINUTES_PER_GOAL,
    ALL_DERIVED_METRICS, MetricDef,
)

logger = logging.getLogger("footiq.quant_tools")


# ─── Configuration ────────────────────────────────────────────────────────────

BASELINES_PATH = Path(__file__).parent / "config" / "baselines.json"
PLOTS_DIR = Path(__file__).parent.parent / "node_gateway" / "public" / "plots"
PER90_MIN_MINUTES = 90


# ─── Baselines Loader ────────────────────────────────────────────────────────

_baselines: dict = {}


def _load_baselines():
    """Load baselines.json once at module init."""
    global _baselines
    if BASELINES_PATH.exists():
        with open(BASELINES_PATH, "r") as f:
            _baselines = json.load(f)
        logger.info(f"Loaded baselines from {BASELINES_PATH}")
    else:
        logger.warning(f"Baselines file not found: {BASELINES_PATH}")


_load_baselines()


def get_baselines() -> dict:
    """Return the loaded baselines (for testing)."""
    return _baselines


# ─── Result Type ──────────────────────────────────────────────────────────────

@dataclass
class QuantResult:
    """Standard return type for all quant functions."""
    value: any = None
    raw_values: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    error: Optional[str] = None


# ─── Per-90 Normalization (STATS_CONFIG §6) ───────────────────────────────────

def compute_per90(games: list[dict], metric_key: str) -> QuantResult:
    """
    Compute per-90 rate for a count metric across multiple games.

    Formula: (sum(metric) / sum(minutes)) * 90
    Threshold: ≥90 total minutes required.

    Args:
        games: List of normalized game dicts (from data_tools._normalize_games)
               Each has {"metrics": {"goals": 2, "minutes_played": 90, ...}}
        metric_key: The metric to compute per-90 for (e.g., "goals")

    Returns:
        QuantResult with value = per-90 rate (float) or None
    """
    warnings = []
    metric_def = KEY_TO_METRIC.get(metric_key)

    if metric_def is None:
        return QuantResult(error=f"Unknown metric: {metric_key}")

    if metric_def.per90_rule == Per90Rule.NA:
        return QuantResult(
            error=f"Metric '{metric_key}' does not support per-90 normalization.",
        )

    # Handle weighted_ratio metrics (shot_accuracy) — delegate to compute_derived
    if metric_def.per90_rule == Per90Rule.WEIGHTED_RATIO:
        return compute_derived(games, metric_key)

    # Collect values, respecting missing semantics
    total_metric = 0
    total_minutes = 0
    has_any_value = False

    for game in games:
        metrics = game.get("metrics", {})
        val = metrics.get(metric_key)
        mins = metrics.get("minutes_played", 0)

        if val is None:
            # Missing semantic — skip this game for this metric
            warnings.append({
                "code": "METRIC_UNAVAILABLE",
                "message": f"Metric '{metric_key}' unavailable for game {game.get('game_id')}",
                "details": {"game_id": game.get("game_id"), "metric": metric_key},
            })
            continue

        total_metric += val
        total_minutes += mins
        has_any_value = True

    if not has_any_value:
        return QuantResult(
            value=None,
            warnings=[{
                "code": "METRIC_UNAVAILABLE",
                "message": f"Metric '{metric_key}' unavailable across all games.",
                "details": {"metric": metric_key},
            }],
        )

    # Check minutes threshold
    if total_minutes < PER90_MIN_MINUTES:
        warnings.append({
            "code": "INSUFFICIENT_MINUTES",
            "message": f"Total minutes ({total_minutes}) below threshold ({PER90_MIN_MINUTES}).",
            "details": {"total_minutes": total_minutes, "threshold": PER90_MIN_MINUTES},
        })
        return QuantResult(value=None, warnings=warnings)

    per90 = (total_metric / total_minutes) * 90
    return QuantResult(value=per90, warnings=warnings)


# ─── Derived Metrics (STATS_CONFIG §4) ────────────────────────────────────────

def compute_derived(games: list[dict], metric_key: str) -> QuantResult:
    """
    Compute a derived metric across multiple games.

    Handles: shot_accuracy, goal_involvement, xg_overperformance, minutes_per_goal.
    Returns METRIC_UNAVAILABLE if required inputs are missing.

    Args:
        games: List of normalized game dicts
        metric_key: The derived metric to compute

    Returns:
        QuantResult with value = computed value or None
    """
    metric_def = KEY_TO_METRIC.get(metric_key)
    if metric_def is None:
        return QuantResult(error=f"Unknown metric: {metric_key}")

    if not metric_def.is_derived:
        return QuantResult(error=f"Metric '{metric_key}' is not a derived metric.")

    if metric_key == "shot_accuracy":
        return _compute_shot_accuracy(games)
    elif metric_key == "goal_involvement":
        return _compute_goal_involvement(games)
    elif metric_key == "xg_overperformance":
        return _compute_xg_overperformance(games)
    elif metric_key == "minutes_per_goal":
        return _compute_minutes_per_goal(games)
    else:
        return QuantResult(error=f"No computation defined for derived metric: {metric_key}")


def _compute_shot_accuracy(games: list[dict]) -> QuantResult:
    """Weighted ratio: sum(shots_on_target) / sum(shots_total)."""
    total_on = 0
    total_shots = 0
    warnings = []

    for game in games:
        m = game.get("metrics", {})
        on_target = m.get("shots_on_target")
        total = m.get("shots_total")

        if on_target is None or total is None:
            warnings.append({
                "code": "METRIC_UNAVAILABLE",
                "message": f"Shot data unavailable for game {game.get('game_id')}",
                "details": {"game_id": game.get("game_id")},
            })
            continue

        total_on += on_target
        total_shots += total

    if total_shots == 0:
        return QuantResult(value=None, warnings=warnings)

    return QuantResult(value=total_on / total_shots, warnings=warnings)


def _compute_goal_involvement(games: list[dict]) -> QuantResult:
    """Additive: sum(goals) + sum(assists)."""
    total_goals = 0
    total_assists = 0

    for game in games:
        m = game.get("metrics", {})
        g = m.get("goals")
        a = m.get("assists")
        if g is not None:
            total_goals += g
        if a is not None:
            total_assists += a

    return QuantResult(value=total_goals + total_assists)


def _compute_xg_overperformance(games: list[dict]) -> QuantResult:
    """goals - expected_goals. Returns None if ANY xG is missing.
    Goals uses true_zero semantic (None → 0), xG uses missing semantic (None → abort)."""
    total_goals = 0
    total_xg = 0
    warnings = []

    for game in games:
        m = game.get("metrics", {})
        g = m.get("goals")
        xg = m.get("expected_goals")

        if xg is None:
            # xG is missing-semantic — cannot compute reliably
            warnings.append({
                "code": "METRIC_UNAVAILABLE",
                "message": f"xG unavailable for game {game.get('game_id')}; cannot compute overperformance.",
                "details": {"game_id": game.get("game_id"), "metric": "expected_goals"},
            })
            return QuantResult(value=None, warnings=warnings)

        # Goals is true_zero: None/absent → 0
        total_goals += g if g is not None else 0
        total_xg += xg

    return QuantResult(value=total_goals - total_xg, warnings=warnings)


def _compute_minutes_per_goal(games: list[dict]) -> QuantResult:
    """sum(minutes) / sum(goals). Returns None if goals == 0."""
    total_mins = 0
    total_goals = 0

    for game in games:
        m = game.get("metrics", {})
        mins = m.get("minutes_played", 0)
        g = m.get("goals", 0)
        total_mins += mins
        total_goals += g

    if total_goals == 0:
        return QuantResult(value=None, warnings=[{
            "code": "METRIC_UNAVAILABLE",
            "message": "Cannot compute minutes_per_goal: zero goals scored.",
            "details": {"total_goals": 0},
        }])

    return QuantResult(value=total_mins / total_goals)


# ─── Z-Score (STATS_CONFIG §9) ───────────────────────────────────────────────

def compute_zscore(
    per90_value: float,
    metric_key: str,
    league: str = "premier_league",
    season: str = "2025_2026",
    position: str = "all_positions",
) -> QuantResult:
    """
    Compute z-score for a per-90 value against league baselines.

    Guardrails (§9.3):
    - Missing baseline → BASELINE_MISSING, return raw value
    - std == 0 → BASELINE_MISSING (zero_variance)
    - n < 30 → BASELINE_MISSING (low_sample)

    Args:
        per90_value: The per-90 rate to evaluate
        metric_key: Which metric baseline to use (e.g., "goals")
        league: League key in baselines.json
        season: Season key
        position: Position group key

    Returns:
        QuantResult with value = z-score (float), or raw per90_value on guardrail fallback
    """
    if per90_value is None:
        return QuantResult(value=None, error="Cannot compute z-score: per90_value is None.")

    # Look up baseline
    baseline = (
        _baselines
        .get(league, {})
        .get(season, {})
        .get(position, {})
        .get(metric_key)
    )

    if baseline is None:
        return QuantResult(
            value=per90_value,
            warnings=[{
                "code": "BASELINE_MISSING",
                "message": f"No baseline for {metric_key} in {league}/{season}/{position}. Returning raw per-90.",
                "details": {
                    "fallback": "raw_per90",
                    "league": league,
                    "season": season,
                    "position": position,
                    "metric": metric_key,
                },
            }],
        )

    mean = baseline.get("mean")
    std = baseline.get("std")
    n = baseline.get("n", 0)

    # Guardrail: std == 0
    if std is None or std == 0:
        return QuantResult(
            value=per90_value,
            warnings=[{
                "code": "BASELINE_MISSING",
                "message": f"Cannot compute z-score: zero variance for {metric_key}. Returning raw per-90.",
                "details": {
                    "fallback": "raw_per90",
                    "reason": "zero_variance",
                    "metric": metric_key,
                },
            }],
        )

    # Guardrail: n < 30
    if n < 30:
        return QuantResult(
            value=per90_value,
            warnings=[{
                "code": "BASELINE_MISSING",
                "message": f"Cannot compute z-score: insufficient sample (n={n}) for {metric_key}. Returning raw per-90.",
                "details": {
                    "fallback": "raw_per90",
                    "reason": "low_sample",
                    "n": n,
                    "metric": metric_key,
                },
            }],
        )

    z = (per90_value - mean) / std
    return QuantResult(value=z)


def interpret_zscore(z: float) -> str:
    """Human-readable z-score interpretation."""
    if z is None:
        return "unavailable"
    abs_z = abs(z)
    direction = "above" if z > 0 else "below"
    if abs_z >= 3.0:
        return f"Extraordinary ({direction} average)"
    elif abs_z >= 2.0:
        return f"Exceptional ({direction} average)"
    elif abs_z >= 1.0:
        return f"Notably {direction} average"
    elif abs_z >= 0.5:
        return f"Slightly {direction} average"
    else:
        return "Average"


# ─── Form Trend ───────────────────────────────────────────────────────────────

def compute_form(
    games: list[dict],
    metric_key: str,
    window: int = 5,
) -> QuantResult:
    """
    Extract per-game values for a metric, most recent first.

    Args:
        games: List of normalized game dicts (assumed most-recent-first)
        metric_key: Metric to extract
        window: Number of games to include

    Returns:
        QuantResult with raw_values = [val1, val2, ...] (most recent first)
    """
    values = []
    game_labels = []

    for game in games[:window]:
        m = game.get("metrics", {})
        val = m.get(metric_key)
        values.append(val)
        game_labels.append(game.get("date", "?"))

    return QuantResult(
        value=len([v for v in values if v is not None]),  # count of available data points
        raw_values=values,
    )


# ─── Plot Generation ─────────────────────────────────────────────────────────

def generate_plot(
    form_data: list,
    player_name: str,
    metric_key: str,
    trace_id: str,
    game_labels: list[str] = None,
    plots_dir: str = None,
) -> QuantResult:
    """
    Generate a form trend line chart and save as PNG.

    Naming: {trace_id}_form-{metric_key}.png (contract-compliant per API_CONTRACT §4.2)
    Output dir: node_gateway/public/plots/ (or custom plots_dir for testing)

    Returns:
        QuantResult with value = relative URL path to the plot
    """
    out_dir = Path(plots_dir) if plots_dir else PLOTS_DIR
    # Sanitize inputs to prevent path traversal
    safe_trace = re.sub(r"[^a-zA-Z0-9_\-]", "_", trace_id)
    safe_metric = re.sub(r"[^a-zA-Z0-9_\-]", "_", metric_key)
    filename = f"{safe_trace}_form-{safe_metric}.png"
    filepath = out_dir / filename

    try:
        # Ensure directory exists
        out_dir.mkdir(parents=True, exist_ok=True)

        # Filter None values for plotting
        plot_values = []
        plot_labels = []
        for i, val in enumerate(form_data):
            if val is not None:
                plot_values.append(val)
                label = game_labels[i] if game_labels and i < len(game_labels) else f"G{i+1}"
                plot_labels.append(label)

        if not plot_values:
            return QuantResult(
                value=None,
                warnings=[{
                    "code": "METRIC_UNAVAILABLE",
                    "message": f"No data points available to plot for {metric_key}.",
                    "details": {"metric": metric_key},
                }],
            )

        # Create plot
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(plot_labels, plot_values, marker="o", linewidth=2, color="#4F46E5")
        ax.fill_between(
            range(len(plot_values)), plot_values,
            alpha=0.1, color="#4F46E5",
        )
        ax.set_title(f"{player_name} — {metric_key.replace('_', ' ').title()} (Last {len(form_data)})")
        ax.set_xlabel("Match Date")
        ax.set_ylabel(KEY_TO_METRIC.get(metric_key, metric_key).display_name
                       if metric_key in KEY_TO_METRIC else metric_key)
        ax.grid(True, alpha=0.3)
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()

        fig.savefig(filepath, dpi=100)
        plt.close(fig)

        relative_url = f"/static/plots/{filename}"
        return QuantResult(value=relative_url)

    except Exception as e:
        logger.error(f"Plot generation failed: {e}")
        return QuantResult(
            value=None,
            error=str(e),
            warnings=[{
                "code": "ARTIFACT_WRITE_FAILED",
                "message": f"Failed to generate plot: {e}",
                "details": {"filepath": str(filepath), "metric": metric_key},
            }],
        )
