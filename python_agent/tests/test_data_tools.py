"""
FootIQ Data Tools — Replay Parity Tests

Tests data_tools.py using fixture-backed replay mode.
Validates: metric extraction, missing-data semantics, normalization,
cache behavior, and error cases.

All values are pre-calculated from the fixtures for deterministic assertions.
"""

import pytest
import asyncio
import httpx
import data_tools
from data_tools import (
    search_entity, get_athlete_games, get_game_lineup,
    clear_cache, _normalize_games, _normalize_lineup,
)
from stats_config import (
    extract_metric_value, GOALS, ASSISTS, MINUTES_PLAYED, RATING,
    EXPECTED_GOALS, SHOTS_TOTAL, SHOTS_ON_TARGET, TOUCHES_IN_BOX,
    KEY_PASSES, TACKLES_WON, YELLOW_CARDS, RED_CARDS,
    MissingSemantic, L1_METRICS, L2_METRICS,
)


# ─── Fixtures (pytest) ──────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_cache():
    """Clear cache before each test."""
    clear_cache()
    yield
    clear_cache()


# ─── search_entity ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_entity_replay_haaland():
    """Single confident match should return 1 result."""
    result = await search_entity("haaland", data_mode="replay")
    assert result.error is None
    assert result.data is not None
    results = result.data["results"]
    assert len(results) == 1
    assert results[0]["entity"]["name"] == "Erling Haaland"
    assert results[0]["entity"]["id"] == 939180
    assert results[0]["entity"]["team"]["name"] == "Manchester City"


@pytest.mark.asyncio
async def test_search_entity_replay_ambiguous():
    """Ambiguous search should return multiple results."""
    result = await search_entity("saka", data_mode="replay")
    assert result.error is None
    results = result.data["results"]
    assert len(results) == 2
    names = [r["entity"]["name"] for r in results]
    assert "Bukayo Saka" in names
    assert "Yaya Saka" in names


@pytest.mark.asyncio
async def test_search_entity_replay_qmissing_empty_results():
    """Replay fixture with empty results should return empty data, not fixture error."""
    result = await search_entity("qmissing", data_mode="replay")
    assert result.error is None
    assert result.data is not None
    assert result.data["results"] == []


@pytest.mark.asyncio
async def test_search_entity_replay_qmulti_ambiguous_fixture():
    """Deterministic ambiguous replay fixture should return >1 entities."""
    result = await search_entity("qmulti", data_mode="replay")
    assert result.error is None
    assert len(result.data["results"]) == 2


@pytest.mark.asyncio
async def test_search_entity_replay_full_name_fallback_haaland():
    """Full name should fallback to surname fixture in replay mode."""
    result = await search_entity("Erling Haaland", data_mode="replay")
    assert result.error is None
    assert result.data is not None
    assert len(result.data["results"]) == 1
    warning = next((w for w in result.warnings if w["code"] == "DATA_MODE_REPLAY"), None)
    assert warning is not None
    assert warning["details"]["fixture"] == "search_entity__haaland.json"


@pytest.mark.asyncio
async def test_search_entity_replay_full_name_fallback_saka():
    """Full name should fallback to surname fixture in replay mode."""
    result = await search_entity("Bukayo Saka", data_mode="replay")
    assert result.error is None
    assert result.data is not None
    assert len(result.data["results"]) == 2
    names = [r["entity"]["name"] for r in result.data["results"]]
    assert "Bukayo Saka" in names
    warning = next((w for w in result.warnings if w["code"] == "DATA_MODE_REPLAY"), None)
    assert warning is not None
    assert warning["details"]["fixture"] == "search_entity__saka.json"


@pytest.mark.asyncio
async def test_search_entity_replay_missing_fixture():
    """Missing fixture should return error, not crash."""
    result = await search_entity("nonexistent_player", data_mode="replay")
    assert result.error is not None
    assert "fixture" in result.error.lower() or "Fixture" in result.error


@pytest.mark.asyncio
async def test_search_entity_cache_hit():
    """Second call should hit cache."""
    r1 = await search_entity("haaland", data_mode="replay")
    assert r1.cache_hit is False

    r2 = await search_entity("haaland", data_mode="replay")
    assert r2.cache_hit is True
    assert r2.data == r1.data
    # Replay cache-hits should preserve replay contract warning.
    warning_codes = [w["code"] for w in r2.warnings]
    assert "DATA_MODE_REPLAY" in warning_codes
    assert "USED_CACHED_DATA" in warning_codes


@pytest.mark.asyncio
async def test_search_entity_live_alias_fallback_when_search_unavailable(monkeypatch):
    """Live mode should use alias map if /search is unavailable on current plan."""
    async def _mock_api_request(endpoint: str, params: dict = None):
        request = httpx.Request("GET", f"https://v1.football.sportsapipro.com{endpoint}")
        response = httpx.Response(status_code=404, request=request)
        raise httpx.HTTPStatusError("Not Found", request=request, response=response)

    monkeypatch.setattr(data_tools, "_api_request", _mock_api_request)

    result = await search_entity("Haaland", data_mode="live", allow_live_fetch=True)
    assert result.error is None
    assert result.data is not None
    assert result.data["results"][0]["entity"]["id"] == 65760
    warning_codes = [w["code"] for w in result.warnings]
    assert "SEARCH_UNAVAILABLE_USING_ALIAS" in warning_codes


@pytest.mark.asyncio
async def test_search_entity_live_no_alias_when_search_unavailable(monkeypatch):
    """Live mode should return explicit error if /search is unavailable and alias is missing."""
    async def _mock_api_request(endpoint: str, params: dict = None):
        request = httpx.Request("GET", f"https://v1.football.sportsapipro.com{endpoint}")
        response = httpx.Response(status_code=404, request=request)
        raise httpx.HTTPStatusError("Not Found", request=request, response=response)

    monkeypatch.setattr(data_tools, "_api_request", _mock_api_request)

    result = await search_entity("Nonexistent Alias Name", data_mode="live", allow_live_fetch=True)
    assert result.error is not None
    warning_codes = [w["code"] for w in result.warnings]
    assert "SEARCH_ENDPOINT_UNAVAILABLE" in warning_codes


@pytest.mark.asyncio
async def test_search_entity_live_alias_substring_when_search_unavailable(monkeypatch):
    """Alias map should match names embedded in a full sentence query."""
    async def _mock_api_request(endpoint: str, params: dict = None):
        request = httpx.Request("GET", f"https://v1.football.sportsapipro.com{endpoint}")
        response = httpx.Response(status_code=404, request=request)
        raise httpx.HTTPStatusError("Not Found", request=request, response=response)

    monkeypatch.setattr(data_tools, "_api_request", _mock_api_request)

    result = await search_entity("show me Haaland's trend", data_mode="live", allow_live_fetch=True)
    assert result.error is None
    assert result.data["results"][0]["entity"]["id"] == 65760
    warning_codes = [w["code"] for w in result.warnings]
    assert "SEARCH_UNAVAILABLE_USING_ALIAS" in warning_codes


@pytest.mark.asyncio
async def test_get_athlete_games_replay_cache_hit_keeps_replay_warning():
    """Replay cache-hits should still include DATA_MODE_REPLAY."""
    r1 = await get_athlete_games(939180, last_n=5, data_mode="replay")
    assert r1.error is None

    r2 = await get_athlete_games(939180, last_n=5, data_mode="replay")
    assert r2.error is None
    assert r2.cache_hit is True
    warning_codes = [w["code"] for w in r2.warnings]
    assert "DATA_MODE_REPLAY" in warning_codes
    assert "USED_CACHED_DATA" in warning_codes


@pytest.mark.asyncio
async def test_get_game_lineup_replay_cache_hit_keeps_replay_warning():
    """Replay cache-hits should still include DATA_MODE_REPLAY."""
    r1 = await get_game_lineup(939180, 11001, data_mode="replay")
    assert r1.error is None

    r2 = await get_game_lineup(939180, 11001, data_mode="replay")
    assert r2.error is None
    assert r2.cache_hit is True
    warning_codes = [w["code"] for w in r2.warnings]
    assert "DATA_MODE_REPLAY" in warning_codes
    assert "USED_CACHED_DATA" in warning_codes


# ─── get_athlete_games (L1 normalization) ─────────────────────────────────────

@pytest.mark.asyncio
async def test_get_athlete_games_replay():
    """Should return normalized game data with L1 metrics."""
    result = await get_athlete_games(939180, last_n=5, data_mode="replay")
    assert result.error is None
    assert len(result.data["games"]) == 5


@pytest.mark.asyncio
async def test_get_athlete_games_replay_saka_fixture_available():
    """Saka replay fixture should be available and normalized."""
    result = await get_athlete_games(934235, last_n=5, data_mode="replay")
    assert result.error is None
    assert len(result.data["games"]) == 5
    g1 = result.data["games"][0]
    assert g1["game_id"] == 21001
    assert g1["metrics"]["goals"] == 1
    assert g1["metrics"]["minutes_played"] == 90


@pytest.mark.asyncio
async def test_get_athlete_games_metrics_extraction():
    """Verify exact metric values from known fixture data.

    Fixture values (Haaland last 5):
    Game 1: goals=2, assists=0, minutes=90, rating=8.2
    Game 2: goals=2, assists=1, minutes=90, rating=9.1
    Game 3: goals=0, assists=1, minutes=78, rating=7.4
    Game 4: goals=1, assists=0, minutes=85, rating=7.8
    Game 5: goals=0, assists=0, minutes=90, rating=6.3
    Totals: goals=5, assists=2, minutes=433
    """
    result = await get_athlete_games(939180, last_n=5, data_mode="replay")
    games = result.data["games"]

    # Game 1 (vs Liverpool)
    g1 = games[0]
    assert g1["metrics"]["goals"] == 2
    assert g1["metrics"]["assists"] == 0
    assert g1["metrics"]["minutes_played"] == 90
    assert g1["metrics"]["rating"] == 8.2

    # Game 5 (vs West Ham)
    g5 = games[4]
    assert g5["metrics"]["goals"] == 0
    assert g5["metrics"]["assists"] == 0
    assert g5["metrics"]["minutes_played"] == 90
    assert g5["metrics"]["rating"] == 6.3

    # Aggregate check
    total_goals = sum(g["metrics"]["goals"] for g in games)
    total_assists = sum(g["metrics"]["assists"] for g in games)
    total_minutes = sum(g["metrics"]["minutes_played"] for g in games)
    assert total_goals == 5
    assert total_assists == 2
    assert total_minutes == 433


@pytest.mark.asyncio
async def test_get_athlete_games_true_zero_semantics():
    """Absent true_zero stats should be 0, not None."""
    result = await get_athlete_games(939180, last_n=5, data_mode="replay")
    for game in result.data["games"]:
        # yellow_cards and red_cards are true_zero — should be 0, never None
        assert game["metrics"]["yellow_cards"] is not None
        assert game["metrics"]["red_cards"] is not None
        assert isinstance(game["metrics"]["yellow_cards"], int)
        assert isinstance(game["metrics"]["red_cards"], int)


@pytest.mark.asyncio
async def test_get_athlete_games_l2_not_extracted():
    """L1 tool should NOT extract L2 metrics (xG, shots, etc.)."""
    result = await get_athlete_games(939180, last_n=5, data_mode="replay")
    for game in result.data["games"]:
        # L2 metrics should not be present in L1 results
        assert "expected_goals" not in game["metrics"]
        assert "shots_total" not in game["metrics"]


@pytest.mark.asyncio
async def test_get_athlete_games_no_normalization_gap():
    """Known fixture data should produce no NORMALIZATION_GAP warnings."""
    result = await get_athlete_games(939180, last_n=5, data_mode="replay")
    assert len(result.data["normalization_warnings"]) == 0


# ─── get_game_lineup (L2 normalization) ───────────────────────────────────────

@pytest.mark.asyncio
async def test_get_game_lineup_replay():
    """Should return all L1+L2 metrics from lineup data."""
    result = await get_game_lineup(939180, 11001, data_mode="replay")
    assert result.error is None
    metrics = result.data["metrics"]

    # L1 metrics
    assert metrics["goals"] == 2
    assert metrics["minutes_played"] == 90
    assert metrics["rating"] == 8.2

    # L2 metrics
    assert metrics["expected_goals"] == 1.35
    assert metrics["shots_total"] == 5
    assert metrics["shots_on_target"] == 3
    assert metrics["touches_in_box"] == 7
    assert metrics["key_passes"] == 1
    assert metrics["tackles_won"] == 0


@pytest.mark.asyncio
async def test_get_game_lineup_position():
    """Position should be extracted from lineup data."""
    result = await get_game_lineup(939180, 11001, data_mode="replay")
    assert result.data["position"] == "ST"


@pytest.mark.asyncio
async def test_get_game_lineup_saka_replay():
    """Saka lineup fixture should load in replay mode."""
    result = await get_game_lineup(934235, 21001, data_mode="replay")
    assert result.error is None
    assert result.data["position"] == "RW"
    assert result.data["metrics"]["expected_goals"] == 0.65


# ─── extract_metric_value (unit tests) ───────────────────────────────────────

def test_extract_present_value():
    """Numeric value present → return as-is."""
    stats = [{"type": 21, "value": 3}]
    assert extract_metric_value(stats, GOALS) == 3


def test_extract_present_null_true_zero():
    """Value is null + true_zero semantic → 0."""
    stats = [{"type": 21, "value": None}]
    assert extract_metric_value(stats, GOALS) == 0


def test_extract_present_null_missing():
    """Value is null + missing semantic → None."""
    stats = [{"type": 42, "value": None}]
    assert extract_metric_value(stats, EXPECTED_GOALS) is None


def test_extract_absent_true_zero():
    """Field absent + true_zero semantic → 0."""
    stats = []  # goals not in array
    assert extract_metric_value(stats, GOALS) == 0


def test_extract_absent_missing():
    """Field absent + missing semantic → None."""
    stats = []  # xG not in array
    assert extract_metric_value(stats, EXPECTED_GOALS) is None


def test_extract_present_zero():
    """Explicit 0 value → always 0 regardless of semantics."""
    stats_zero = [{"type": 21, "value": 0}]
    assert extract_metric_value(stats_zero, GOALS) == 0

    stats_xg_zero = [{"type": 42, "value": 0}]
    assert extract_metric_value(stats_xg_zero, EXPECTED_GOALS) == 0


def test_normalize_games_live_shape_uses_fallback_ids():
    """New live shape (game + athleteStats) should normalize into standard L1 metrics."""
    raw = {
        "games": [
            {
                "game": {
                    "id": 4452657,
                    "startTime": "2026-02-08T16:30:00+00:00",
                    "homeCompetitor": {"id": 108, "name": "Liverpool", "score": 1},
                    "awayCompetitor": {"id": 110, "name": "Manchester City", "score": 1},
                    "scores": [1, 1],
                },
                "relatedCompetitor": 110,
                "athleteStats": [
                    {"type": 229, "value": "90"},   # minutes_played fallback
                    {"type": 225, "value": "1"},    # goals fallback
                    {"type": 226, "value": "0"},    # assists fallback
                    {"type": 0, "value": "7.2"},    # rating fallback
                ],
            }
        ]
    }

    normalized = _normalize_games(raw)
    assert len(normalized["games"]) == 1
    g = normalized["games"][0]
    assert g["game_id"] == 4452657
    assert g["date"] == "2026-02-08T16:30:00+00:00"
    assert g["score"] == "1-1"
    assert g["opponent"] == "Liverpool"
    assert g["metrics"]["minutes_played"] == 90
    assert g["metrics"]["goals"] == 1
    assert g["metrics"]["assists"] == 0
    assert g["metrics"]["rating"] == 7.2
    assert len(normalized["normalization_warnings"]) == 0


def test_normalize_lineup_live_shape_uses_fallback_ids():
    """Lineup normalization should handle athleteStats in live-shape payloads."""
    raw = {
        "lineup": {
            "game": {"id": 4452657},
            "athleteId": 65760,
            "position": {"name": "Attacker"},
            "athleteStats": [
                {"type": 229, "value": "90"},
                {"type": 225, "value": "1"},
                {"type": 226, "value": "0"},
                {"type": 0, "value": "7.8"},
            ],
        }
    }

    normalized = _normalize_lineup(raw)
    assert normalized["game_id"] == 4452657
    assert normalized["athlete_id"] == 65760
    assert normalized["position"] == "Attacker"
    assert normalized["metrics"]["minutes_played"] == 90
    assert normalized["metrics"]["goals"] == 1
    assert normalized["metrics"]["assists"] == 0
    assert normalized["metrics"]["rating"] == 7.8


# ─── Cache-only mode ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cache_only_no_data():
    """cache-only with empty cache should return error."""
    result = await search_entity("haaland", data_mode="live", allow_live_fetch=False)
    assert result.error is not None
    warning_codes = [w["code"] for w in result.warnings]
    assert "CACHE_ONLY_MODE" in warning_codes


@pytest.mark.asyncio
async def test_cache_only_with_replay_primed_cache_does_not_leak_to_live():
    """Replay cache entries must not satisfy live-mode cache-only requests."""
    r1 = await search_entity("haaland", data_mode="replay")
    assert r1.error is None

    r2 = await search_entity("haaland", data_mode="live", allow_live_fetch=False)
    assert r2.error is not None
    warning_codes = [w["code"] for w in r2.warnings]
    assert "CACHE_ONLY_MODE" in warning_codes


@pytest.mark.asyncio
async def test_cache_only_with_live_primed_cache_succeeds(monkeypatch):
    """Live cache-only should work when live cache was primed first."""
    async def _mock_api_request(endpoint: str, params: dict = None):
        assert endpoint == "/search"
        return {
            "results": [
                {
                    "type": "player",
                    "entity": {"id": 65760, "name": "Erling Haaland", "team": {"name": "Manchester City"}},
                    "score": 100.0,
                }
            ]
        }

    monkeypatch.setattr(data_tools, "_api_request", _mock_api_request)

    r1 = await search_entity("haaland", data_mode="live", allow_live_fetch=True)
    assert r1.error is None
    assert r1.cache_hit is False

    r2 = await search_entity("haaland", data_mode="live", allow_live_fetch=False)
    assert r2.error is None
    assert r2.cache_hit is True


# ─── Replay mode warnings ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_replay_mode_emits_warning():
    """Every replay call should emit DATA_MODE_REPLAY warning."""
    result = await search_entity("haaland", data_mode="replay")
    warning_codes = [w["code"] for w in result.warnings]
    assert "DATA_MODE_REPLAY" in warning_codes


@pytest.mark.asyncio
async def test_replay_mode_never_calls_api(monkeypatch):
    """Replay mode should never call the upstream API client."""
    async def _boom(*args, **kwargs):
        raise AssertionError("Replay mode must not call _api_request")

    monkeypatch.setattr(data_tools, "_api_request", _boom)

    r1 = await search_entity("haaland", data_mode="replay")
    assert r1.error is None

    r2 = await get_athlete_games(939180, last_n=5, data_mode="replay")
    assert r2.error is None

    r3 = await get_game_lineup(939180, 11001, data_mode="replay")
    assert r3.error is None
