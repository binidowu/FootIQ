"""
FootIQ Stats Configuration — Python Registry

Source of truth: docs/STATS_CONFIG.md
This module translates the documented metric table into code-level
constants used by data_tools.py and quant_tools.py.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ─── Enums ────────────────────────────────────────────────────────────────────

class Availability(str, Enum):
    L1 = "L1"
    L2 = "L2"


class MissingSemantic(str, Enum):
    TRUE_ZERO = "true_zero"   # null/absent → 0 (event didn't happen)
    MISSING = "missing"       # null/absent → None (data not collected)


class Per90Rule(str, Enum):
    PER90_BY_MINUTES = "per90_by_minutes"   # sum(metric) / sum(minutes) * 90
    WEIGHTED_RATIO = "weighted_ratio"       # sum(numerator) / sum(denominator)
    NA = "na"                               # No per-90 (already normalized or denominator)


# ─── Metric Definition ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class MetricDef:
    api_type_id: Optional[int]     # SportsAPIPro stat type ID (None for derived)
    key: str                       # Internal key used throughout the system
    display_name: str
    data_type: str                 # "int", "float", "percentage"
    unit: str
    availability: Optional[Availability]  # None for derived metrics
    missing_semantic: MissingSemantic
    per90_rule: Per90Rule
    notes: str = ""
    # For weighted_ratio metrics
    numerator_key: Optional[str] = None
    denominator_key: Optional[str] = None
    # For derived metrics
    is_derived: bool = False
    required_inputs: tuple = field(default_factory=tuple)


# ─── L1 Metrics (Always Available) ───────────────────────────────────────────

RATING = MetricDef(
    api_type_id=10, key="rating", display_name="Match Rating",
    data_type="float", unit="0-10 scale",
    availability=Availability.L1,
    missing_semantic=MissingSemantic.MISSING,
    per90_rule=Per90Rule.NA,
    notes="SofaScore-style composite",
)

GOALS = MetricDef(
    api_type_id=21, key="goals", display_name="Goals",
    data_type="int", unit="count",
    availability=Availability.L1,
    missing_semantic=MissingSemantic.TRUE_ZERO,
    per90_rule=Per90Rule.PER90_BY_MINUTES,
    notes="Outfield only",
)

ASSISTS = MetricDef(
    api_type_id=22, key="assists", display_name="Assists",
    data_type="int", unit="count",
    availability=Availability.L1,
    missing_semantic=MissingSemantic.TRUE_ZERO,
    per90_rule=Per90Rule.PER90_BY_MINUTES,
)

MINUTES_PLAYED = MetricDef(
    api_type_id=11, key="minutes_played", display_name="Minutes Played",
    data_type="int", unit="minutes",
    availability=Availability.L1,
    missing_semantic=MissingSemantic.TRUE_ZERO,
    per90_rule=Per90Rule.NA,
    notes="Used as denominator for per-90",
)

YELLOW_CARDS = MetricDef(
    api_type_id=14, key="yellow_cards", display_name="Yellow Cards",
    data_type="int", unit="count",
    availability=Availability.L1,
    missing_semantic=MissingSemantic.TRUE_ZERO,
    per90_rule=Per90Rule.PER90_BY_MINUTES,
)

RED_CARDS = MetricDef(
    api_type_id=15, key="red_cards", display_name="Red Cards",
    data_type="int", unit="count",
    availability=Availability.L1,
    missing_semantic=MissingSemantic.TRUE_ZERO,
    per90_rule=Per90Rule.PER90_BY_MINUTES,
)


# ─── L2 Metrics (Detailed Lineups Only) ──────────────────────────────────────

EXPECTED_GOALS = MetricDef(
    api_type_id=42, key="expected_goals", display_name="Expected Goals (xG)",
    data_type="float", unit="xG",
    availability=Availability.L2,
    missing_semantic=MissingSemantic.MISSING,
    per90_rule=Per90Rule.PER90_BY_MINUTES,
    notes="Opta-sourced; not available in all leagues",
)

SHOTS_TOTAL = MetricDef(
    api_type_id=56, key="shots_total", display_name="Total Shots",
    data_type="int", unit="count",
    availability=Availability.L2,
    missing_semantic=MissingSemantic.MISSING,
    per90_rule=Per90Rule.PER90_BY_MINUTES,
    notes="Denominator for accuracy",
)

SHOTS_ON_TARGET = MetricDef(
    api_type_id=57, key="shots_on_target", display_name="Shots on Target",
    data_type="int", unit="count",
    availability=Availability.L2,
    missing_semantic=MissingSemantic.MISSING,
    per90_rule=Per90Rule.PER90_BY_MINUTES,
    notes="Numerator for accuracy",
)

TOUCHES_IN_BOX = MetricDef(
    api_type_id=55, key="touches_in_box", display_name="Touches in Penalty Box",
    data_type="int", unit="count",
    availability=Availability.L2,
    missing_semantic=MissingSemantic.MISSING,
    per90_rule=Per90Rule.PER90_BY_MINUTES,
    notes="Positional involvement",
)

KEY_PASSES = MetricDef(
    api_type_id=45, key="key_passes", display_name="Key Passes",
    data_type="int", unit="count",
    availability=Availability.L2,
    missing_semantic=MissingSemantic.MISSING,
    per90_rule=Per90Rule.PER90_BY_MINUTES,
    notes="Chance creation",
)

TACKLES_WON = MetricDef(
    api_type_id=78, key="tackles_won", display_name="Tackles Won",
    data_type="int", unit="count",
    availability=Availability.L2,
    missing_semantic=MissingSemantic.MISSING,
    per90_rule=Per90Rule.PER90_BY_MINUTES,
    notes="Defensive metric",
)


# ─── Derived Metrics ─────────────────────────────────────────────────────────

SHOT_ACCURACY = MetricDef(
    api_type_id=None, key="shot_accuracy", display_name="Shot Accuracy",
    data_type="percentage", unit="%",
    availability=None,
    missing_semantic=MissingSemantic.MISSING,
    per90_rule=Per90Rule.WEIGHTED_RATIO,
    numerator_key="shots_on_target", denominator_key="shots_total",
    is_derived=True, required_inputs=("shots_on_target", "shots_total"),
    notes="Weighted ratio: sum(on_target)/sum(total)",
)

GOAL_INVOLVEMENT = MetricDef(
    api_type_id=None, key="goal_involvement", display_name="Goal Involvement",
    data_type="int", unit="count",
    availability=None,
    missing_semantic=MissingSemantic.TRUE_ZERO,
    per90_rule=Per90Rule.PER90_BY_MINUTES,
    is_derived=True, required_inputs=("goals", "assists"),
)

XG_OVERPERFORMANCE = MetricDef(
    api_type_id=None, key="xg_overperformance", display_name="xG Overperformance",
    data_type="float", unit="goals - xG",
    availability=None,
    missing_semantic=MissingSemantic.MISSING,
    per90_rule=Per90Rule.NA,
    is_derived=True, required_inputs=("goals", "expected_goals"),
)

MINUTES_PER_GOAL = MetricDef(
    api_type_id=None, key="minutes_per_goal", display_name="Minutes per Goal",
    data_type="float", unit="minutes",
    availability=None,
    missing_semantic=MissingSemantic.MISSING,
    per90_rule=Per90Rule.NA,
    is_derived=True, required_inputs=("minutes_played", "goals"),
)


# ─── Registries (Lookup Tables) ──────────────────────────────────────────────

# All raw (non-derived) metrics
ALL_RAW_METRICS: list[MetricDef] = [
    RATING, GOALS, ASSISTS, MINUTES_PLAYED, YELLOW_CARDS, RED_CARDS,
    EXPECTED_GOALS, SHOTS_TOTAL, SHOTS_ON_TARGET, TOUCHES_IN_BOX, KEY_PASSES, TACKLES_WON,
]

# All derived metrics
ALL_DERIVED_METRICS: list[MetricDef] = [
    SHOT_ACCURACY, GOAL_INVOLVEMENT, XG_OVERPERFORMANCE, MINUTES_PER_GOAL,
]

# Lookup: API type ID → MetricDef
TYPE_ID_TO_METRIC: dict[int, MetricDef] = {
    m.api_type_id: m for m in ALL_RAW_METRICS if m.api_type_id is not None
}

# Lookup: metric key → MetricDef
KEY_TO_METRIC: dict[str, MetricDef] = {
    m.key: m for m in ALL_RAW_METRICS + ALL_DERIVED_METRICS
}

# L1-only metrics
L1_METRICS: list[MetricDef] = [m for m in ALL_RAW_METRICS if m.availability == Availability.L1]
L2_METRICS: list[MetricDef] = [m for m in ALL_RAW_METRICS if m.availability == Availability.L2]

# Minimum minutes for per-90 calculation
PER90_MIN_MINUTES = 90


def extract_metric_value(statistics: list[dict], metric: MetricDef) -> any:
    """
    Extract a metric value from a SportsAPIPro statistics array.
    Applies field-presence rules per STATS_CONFIG.md §5.2.

    Args:
        statistics: List of {"type": int, "value": any} dicts
        metric: The MetricDef to extract

    Returns:
        The metric value (int/float), 0 (for true_zero), or None (for missing)
    """
    if metric.api_type_id is None:
        return None  # Derived metrics aren't extracted from API

    for stat in statistics:
        if stat.get("type") == metric.api_type_id:
            value = stat.get("value")
            if value is not None:
                return value
            # Field present but value is null
            if metric.missing_semantic == MissingSemantic.TRUE_ZERO:
                return 0
            return None  # missing semantic

    # Field absent from array
    if metric.missing_semantic == MissingSemantic.TRUE_ZERO:
        return 0
    return None  # missing semantic
