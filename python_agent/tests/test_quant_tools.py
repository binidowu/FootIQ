"""
FootIQ Quantitative Tools — Tests

Tests quant_tools.py using fixture data from Phase 2.
All numeric assertions use pytest.approx to avoid brittle rounding failures.

Pre-calculated fixture values (Haaland last 5 games):
  goals: 2+2+0+1+0 = 5,  assists: 0+1+1+0+0 = 2
  minutes: 90+90+78+85+90 = 433
  ratings: 8.2, 9.1, 7.4, 7.8, 6.3

L2 fixture (game 11001):
  xG=1.35, shots_total=5, shots_on_target=3, touches_in_box=7
"""

import os
import shutil
import tempfile
import pytest
from pytest import approx

from quant_tools import (
    compute_per90, compute_derived, compute_zscore,
    compute_form, generate_plot, interpret_zscore, QuantResult,
    _baselines,
)


# ─── Fixtures (pytest) ──────────────────────────────────────────────────────

@pytest.fixture
def haaland_5_games():
    """Normalized L1 games (from replay fixture)."""
    return [
        {"game_id": 11001, "date": "2026-02-08", "metrics": {"goals": 2, "assists": 0, "minutes_played": 90, "rating": 8.2, "yellow_cards": 0, "red_cards": 0}},
        {"game_id": 11002, "date": "2026-02-01", "metrics": {"goals": 2, "assists": 1, "minutes_played": 90, "rating": 9.1, "yellow_cards": 0, "red_cards": 0}},
        {"game_id": 11003, "date": "2026-01-25", "metrics": {"goals": 0, "assists": 1, "minutes_played": 78, "rating": 7.4, "yellow_cards": 1, "red_cards": 0}},
        {"game_id": 11004, "date": "2026-01-18", "metrics": {"goals": 1, "assists": 0, "minutes_played": 85, "rating": 7.8, "yellow_cards": 0, "red_cards": 0}},
        {"game_id": 11005, "date": "2026-01-11", "metrics": {"goals": 0, "assists": 0, "minutes_played": 90, "rating": 6.3, "yellow_cards": 0, "red_cards": 0}},
    ]


@pytest.fixture
def l2_single_game():
    """Normalized L2 lineup data (from replay fixture)."""
    return [
        {
            "game_id": 11001, "date": "2026-02-08",
            "metrics": {
                "goals": 2, "assists": 0, "minutes_played": 90, "rating": 8.2,
                "expected_goals": 1.35, "shots_total": 5, "shots_on_target": 3,
                "touches_in_box": 7, "key_passes": 1, "tackles_won": 0,
                "yellow_cards": 0, "red_cards": 0,
            },
        },
    ]


@pytest.fixture
def low_minutes_games():
    """Games with total minutes < 90."""
    return [
        {"game_id": 1, "date": "2026-01-01", "metrics": {"goals": 1, "minutes_played": 30}},
        {"game_id": 2, "date": "2026-01-02", "metrics": {"goals": 1, "minutes_played": 25}},
    ]


@pytest.fixture
def missing_xg_games():
    """Games where xG is None (missing-semantic)."""
    return [
        {"game_id": 1, "date": "2026-01-01", "metrics": {"goals": 2, "expected_goals": 1.0, "minutes_played": 90}},
        {"game_id": 2, "date": "2026-01-02", "metrics": {"goals": 1, "expected_goals": None, "minutes_played": 90}},
    ]


@pytest.fixture
def zero_goals_games():
    """Games with zero goals for minutes_per_goal edge case."""
    return [
        {"game_id": 1, "date": "2026-01-01", "metrics": {"goals": 0, "minutes_played": 90}},
        {"game_id": 2, "date": "2026-01-02", "metrics": {"goals": 0, "minutes_played": 90}},
    ]


@pytest.fixture
def tmp_plots_dir():
    """Temporary directory for plot tests."""
    d = tempfile.mkdtemp(prefix="footiq_plots_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ─── Per-90 Tests ─────────────────────────────────────────────────────────────

def test_per90_goals(haaland_5_games):
    """Per-90 goals: (5/433)*90 = 1.039..."""
    result = compute_per90(haaland_5_games, "goals")
    assert result.error is None
    assert result.value == approx((5 / 433) * 90, rel=1e-3)


def test_per90_assists(haaland_5_games):
    """Per-90 assists: (2/433)*90 = 0.415..."""
    result = compute_per90(haaland_5_games, "assists")
    assert result.error is None
    assert result.value == approx((2 / 433) * 90, rel=1e-3)


def test_per90_insufficient_minutes(low_minutes_games):
    """Should return None + INSUFFICIENT_MINUTES when total < 90."""
    result = compute_per90(low_minutes_games, "goals")
    assert result.value is None
    warning_codes = [w["code"] for w in result.warnings]
    assert "INSUFFICIENT_MINUTES" in warning_codes


def test_per90_na_metric(haaland_5_games):
    """rating has per90_rule=NA, should error."""
    result = compute_per90(haaland_5_games, "rating")
    assert result.error is not None
    assert "per-90" in result.error.lower()


def test_per90_unknown_metric(haaland_5_games):
    """Unknown metric should error."""
    result = compute_per90(haaland_5_games, "nonexistent")
    assert result.error is not None


def test_per90_all_none_metric():
    """All None values should return None + METRIC_UNAVAILABLE."""
    games = [
        {"game_id": 1, "metrics": {"expectations": None, "minutes_played": 90, "expected_goals": None}},
        {"game_id": 2, "metrics": {"expectations": None, "minutes_played": 90, "expected_goals": None}},
    ]
    result = compute_per90(games, "expected_goals")
    assert result.value is None
    warning_codes = [w["code"] for w in result.warnings]
    assert "METRIC_UNAVAILABLE" in warning_codes


# ─── Derived Metrics Tests ───────────────────────────────────────────────────

def test_shot_accuracy(l2_single_game):
    """Weighted: 3/5 = 0.60."""
    result = compute_derived(l2_single_game, "shot_accuracy")
    assert result.error is None
    assert result.value == approx(3 / 5, rel=1e-3)


def test_goal_involvement(haaland_5_games):
    """Additive: 5 goals + 2 assists = 7."""
    result = compute_derived(haaland_5_games, "goal_involvement")
    assert result.error is None
    assert result.value == 7


def test_xg_overperformance(l2_single_game):
    """goals(2) - xG(1.35) = 0.65."""
    result = compute_derived(l2_single_game, "xg_overperformance")
    assert result.error is None
    assert result.value == approx(2 - 1.35, rel=1e-3)


def test_xg_overperformance_missing_xg(missing_xg_games):
    """If ANY xG is None, return None + METRIC_UNAVAILABLE."""
    result = compute_derived(missing_xg_games, "xg_overperformance")
    assert result.value is None
    warning_codes = [w["code"] for w in result.warnings]
    assert "METRIC_UNAVAILABLE" in warning_codes


def test_minutes_per_goal(haaland_5_games):
    """433 minutes / 5 goals = 86.6."""
    result = compute_derived(haaland_5_games, "minutes_per_goal")
    assert result.error is None
    assert result.value == approx(433 / 5, rel=1e-3)


def test_minutes_per_goal_zero_goals(zero_goals_games):
    """Zero goals → None + METRIC_UNAVAILABLE."""
    result = compute_derived(zero_goals_games, "minutes_per_goal")
    assert result.value is None
    warning_codes = [w["code"] for w in result.warnings]
    assert "METRIC_UNAVAILABLE" in warning_codes


def test_derived_non_derived_metric(haaland_5_games):
    """Trying to compute derived for a raw metric should error."""
    result = compute_derived(haaland_5_games, "goals")
    assert result.error is not None


# ─── Z-Score Tests ────────────────────────────────────────────────────────────

def test_zscore_normal():
    """Z = (1.039 - 0.25) / 0.22 = 3.59 (approx)."""
    per90 = (5 / 433) * 90  # 1.039...
    result = compute_zscore(per90, metric_key="goals")
    assert result.error is None
    expected_z = (per90 - 0.25) / 0.22
    assert result.value == approx(expected_z, rel=1e-3)


def test_zscore_missing_baseline():
    """Unknown league → BASELINE_MISSING, but returns raw per-90 value."""
    result = compute_zscore(1.0, metric_key="goals", league="serie_a")
    # Fallback: raw per-90 returned, not None (per STATS_CONFIG §9.3)
    assert result.value == approx(1.0)
    warning_codes = [w["code"] for w in result.warnings]
    assert "BASELINE_MISSING" in warning_codes
    assert result.warnings[0]["details"]["fallback"] == "raw_per90"


def test_zscore_missing_metric_baseline():
    """Metric not in baseline → BASELINE_MISSING, returns raw value."""
    result = compute_zscore(1.0, metric_key="touches_in_box")
    assert result.value == approx(1.0)
    warning_codes = [w["code"] for w in result.warnings]
    assert "BASELINE_MISSING" in warning_codes


def test_zscore_none_input():
    """None per90 → error."""
    result = compute_zscore(None, metric_key="goals")
    assert result.error is not None


def test_zscore_interpretation():
    """Test z-score interpretation labels."""
    assert interpret_zscore(3.5) == "Extraordinary (above average)"
    assert interpret_zscore(2.5) == "Exceptional (above average)"
    assert interpret_zscore(1.5) == "Notably above average"
    assert interpret_zscore(0.7) == "Slightly above average"
    assert interpret_zscore(0.2) == "Average"
    assert interpret_zscore(-1.5) == "Notably below average"
    assert interpret_zscore(None) == "unavailable"


# ─── Form Tests ───────────────────────────────────────────────────────────────

def test_form_ordering(haaland_5_games):
    """Form values should match fixture order (most recent first)."""
    result = compute_form(haaland_5_games, "goals")
    assert result.raw_values == [2, 2, 0, 1, 0]


def test_form_window(haaland_5_games):
    """Window=3 should return only 3 most recent."""
    result = compute_form(haaland_5_games, "goals", window=3)
    assert len(result.raw_values) == 3
    assert result.raw_values == [2, 2, 0]


def test_form_rating(haaland_5_games):
    """Rating form should match fixture values."""
    result = compute_form(haaland_5_games, "rating")
    assert result.raw_values == [8.2, 9.1, 7.4, 7.8, 6.3]


# ─── Plot Tests ───────────────────────────────────────────────────────────────

def test_plot_generates_file(tmp_plots_dir):
    """Plot should create a PNG file at the expected path."""
    result = generate_plot(
        form_data=[2, 2, 0, 1, 0],
        player_name="Erling Haaland",
        metric_key="goals",
        trace_id="ftiq_test_001",
        game_labels=["Feb 8", "Feb 1", "Jan 25", "Jan 18", "Jan 11"],
        plots_dir=tmp_plots_dir,
    )
    assert result.error is None
    assert result.value == "/static/plots/ftiq_test_001_form-goals.png"

    # File should actually exist
    expected_path = os.path.join(tmp_plots_dir, "ftiq_test_001_form-goals.png")
    assert os.path.exists(expected_path)
    assert os.path.getsize(expected_path) > 0


def test_plot_no_data_points(tmp_plots_dir):
    """All None data should return METRIC_UNAVAILABLE, no file."""
    result = generate_plot(
        form_data=[None, None, None],
        player_name="Test Player",
        metric_key="expected_goals",
        trace_id="ftiq_test_002",
        plots_dir=tmp_plots_dir,
    )
    assert result.value is None
    warning_codes = [w["code"] for w in result.warnings]
    assert "METRIC_UNAVAILABLE" in warning_codes


def test_plot_failure_path():
    """Write to unwritable path → ARTIFACT_WRITE_FAILED, no crash."""
    result = generate_plot(
        form_data=[1, 2, 3],
        player_name="Test Player",
        metric_key="goals",
        trace_id="ftiq_fail_test",
        plots_dir="/nonexistent/readonly/path/surely",
    )
    # Should not raise — should return error gracefully
    assert result.value is None
    warning_codes = [w["code"] for w in result.warnings]
    assert "ARTIFACT_WRITE_FAILED" in warning_codes


def test_plot_contract_naming(tmp_plots_dir):
    """Filename must follow {trace_id}_form-{metric_key}.png."""
    result = generate_plot(
        form_data=[1, 2],
        player_name="Test",
        metric_key="assists",
        trace_id="ftiq_abc_123",
        plots_dir=tmp_plots_dir,
    )
    assert "ftiq_abc_123_form-assists.png" in result.value


# ─── Z-Score Guardrail Edge Cases ─────────────────────────────────────────────

def test_zscore_zero_variance():
    """std==0 → BASELINE_MISSING (zero_variance), returns raw per-90."""
    # Temporarily inject a zero-variance baseline
    _baselines.setdefault("test_league", {}).setdefault("2025_2026", {}).setdefault(
        "all_positions", {}
    )["goals"] = {"mean": 0.25, "std": 0, "n": 200}
    try:
        result = compute_zscore(1.0, metric_key="goals", league="test_league")
        assert result.value == approx(1.0)  # raw per-90 returned
        warning_codes = [w["code"] for w in result.warnings]
        assert "BASELINE_MISSING" in warning_codes
        assert result.warnings[0]["details"]["reason"] == "zero_variance"
        assert result.warnings[0]["details"]["fallback"] == "raw_per90"
    finally:
        del _baselines["test_league"]


def test_zscore_low_sample():
    """n<30 → BASELINE_MISSING (low_sample), returns raw per-90."""
    _baselines.setdefault("test_league", {}).setdefault("2025_2026", {}).setdefault(
        "all_positions", {}
    )["goals"] = {"mean": 0.25, "std": 0.22, "n": 15}
    try:
        result = compute_zscore(1.0, metric_key="goals", league="test_league")
        assert result.value == approx(1.0)  # raw per-90 returned
        warning_codes = [w["code"] for w in result.warnings]
        assert "BASELINE_MISSING" in warning_codes
        assert result.warnings[0]["details"]["reason"] == "low_sample"
        assert result.warnings[0]["details"]["n"] == 15
    finally:
        del _baselines["test_league"]


# ─── xG Edge Cases ────────────────────────────────────────────────────────────

def test_xg_overperformance_null_goals_true_zero():
    """Goals uses true_zero: null goals → treated as 0, xG still accumulated."""
    games = [
        {"game_id": 1, "metrics": {"goals": None, "expected_goals": 0.5}},
        {"game_id": 2, "metrics": {"goals": 2, "expected_goals": 1.0}},
    ]
    result = compute_derived(games, "xg_overperformance")
    # (0 + 2) - (0.5 + 1.0) = 0.5
    assert result.value == approx(0.5, rel=1e-3)


# ─── Filename Sanitization ────────────────────────────────────────────────────

def test_plot_sanitizes_path_traversal(tmp_plots_dir):
    """Trace ID with path separators should be sanitized."""
    result = generate_plot(
        form_data=[1, 2, 3],
        player_name="Test",
        metric_key="goals",
        trace_id="../../etc/passwd",
        plots_dir=tmp_plots_dir,
    )
    assert result.error is None
    # Should NOT contain path separators in the filename
    assert "/" not in result.value.split("/static/plots/")[1]
    assert ".." not in result.value
    # File should be in the intended directory
    import glob
    files = glob.glob(os.path.join(tmp_plots_dir, "*.png"))
    assert len(files) == 1

