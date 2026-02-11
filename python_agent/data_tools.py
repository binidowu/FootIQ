"""
FootIQ Data Tools — API Client, Cache, Replay Mode, Metric Extraction

Provides LangChain-compatible tool functions for:
- search_entity: Find a player/team by name
- get_athlete_games: Fetch recent game summaries (L1)
- get_game_lineup: Fetch detailed per-game stats (L2)

Supports three data modes:
- live: Real API calls with TTL cache
- replay: Load from fixtures (no network)
- cache-only: allow_live_fetch=False, return stale cache or error
"""

import json
import time
import os
import logging
import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

import httpx

from stats_config import (
    ALL_RAW_METRICS, L1_METRICS, L2_METRICS,
    TYPE_ID_TO_METRIC, KEY_TO_METRIC, MetricDef,
    MissingSemantic, extract_metric_value,
)

logger = logging.getLogger("footiq.data_tools")


# ─── Configuration ────────────────────────────────────────────────────────────

API_BASE_URL = os.getenv("SPORTAPI_BASE_URL", "https://v1.football.sportsapipro.com")
API_KEY = os.getenv("SPORTAPI_KEY", "")

FIXTURE_DIR = Path(__file__).parent / "tests" / "fixtures" / "sportapi"
CACHE_TTL_S = int(os.getenv("CACHE_TTL_S", "1800"))  # 30 minutes default

# Fallback alias map for plans where /search is not available.
# Keys must be normalized with _normalize_query_key.
LIVE_PLAYER_ALIASES = {
    "haaland": {"athlete_id": 65760, "name": "Erling Haaland", "team": "Manchester City"},
    "erling haaland": {"athlete_id": 65760, "name": "Erling Haaland", "team": "Manchester City"},
    "bellingham": {"athlete_id": 73000, "name": "Jude Bellingham", "team": "Real Madrid"},
    "jude bellingham": {"athlete_id": 73000, "name": "Jude Bellingham", "team": "Real Madrid"},
    "de bruyne": {"athlete_id": 843, "name": "Kevin De Bruyne", "team": "Manchester City"},
    "kevin de bruyne": {"athlete_id": 843, "name": "Kevin De Bruyne", "team": "Manchester City"},
    "mbappe": {"athlete_id": 39820, "name": "Kylian Mbappe", "team": "Real Madrid"},
    "kylian mbappe": {"athlete_id": 39820, "name": "Kylian Mbappe", "team": "Real Madrid"},
}

# Newer SportsAPI plans expose different stat type IDs in live mode.
# Keep canonical IDs in stats_config.py; use these as best-effort fallbacks only
# when canonical IDs are absent.
LIVE_TYPE_ID_FALLBACKS = {
    "rating": (0,),
    "minutes_played": (229,),
    "goals": (225,),
    "assists": (226, 1),
}


# ─── TTL Cache ────────────────────────────────────────────────────────────────

@dataclass
class CacheEntry:
    data: any
    created_at: float
    ttl_s: int = CACHE_TTL_S

    @property
    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl_s

    @property
    def ttl_remaining_s(self) -> int:
        remaining = self.ttl_s - (time.time() - self.created_at)
        return max(0, int(remaining))


class TTLCache:
    """Simple in-memory TTL cache for API responses."""

    def __init__(self, default_ttl_s: int = CACHE_TTL_S):
        self._store: dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl_s

    def get(self, key: str) -> Optional[CacheEntry]:
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.is_expired:
            del self._store[key]
            return None
        return entry

    def set(self, key: str, data: any, ttl_s: int = None):
        self._store[key] = CacheEntry(
            data=data,
            created_at=time.time(),
            ttl_s=ttl_s or self._default_ttl,
        )

    def clear(self):
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)


# Global cache instance
_cache = TTLCache()


# ─── Fixture Loader (Replay Mode) ────────────────────────────────────────────

def _load_fixture(filename: str) -> Optional[dict]:
    """Load a JSON fixture file. Returns None if not found."""
    filepath = FIXTURE_DIR / filename
    if filepath.exists():
        with open(filepath, "r") as f:
            return json.load(f)
    logger.warning(f"Fixture not found: {filepath}")
    return None


def _make_replay_warning(fixture: Optional[str] = None, source: str = "fixture") -> dict:
    """Build a standard replay-mode warning payload."""
    details = {"source": source}
    if fixture:
        details["fixture"] = fixture
    return {
        "code": "DATA_MODE_REPLAY",
        "message": "DATA_MODE=replay active. Using static fixtures.",
        "details": details,
    }


def _search_fixture_candidates(query: str) -> list[str]:
    """
    Build fallback fixture candidates for replay-mode search.

    This keeps replay stable when upstream prompts expand a short query
    (e.g. "haaland" -> "erling haaland").
    """
    cleaned = re.sub(r"[^a-z0-9\\s_-]", " ", query.lower())
    normalized = " ".join(cleaned.split())
    tokens = [t for t in normalized.split(" ") if t]

    candidates = []
    if normalized:
        candidates.append(f"search_entity__{normalized}.json")
        candidates.append(f"search_entity__{normalized.replace(' ', '-')}.json")
        candidates.append(f"search_entity__{normalized.replace(' ', '_')}.json")

    if len(tokens) > 1:
        # Prefer last token (surname) as first fallback.
        candidates.append(f"search_entity__{tokens[-1]}.json")
        candidates.append(f"search_entity__{tokens[0]}.json")

    # De-duplicate while preserving order.
    deduped = []
    seen = set()
    for name in candidates:
        if name not in seen:
            seen.add(name)
            deduped.append(name)
    return deduped


def _normalize_query_key(query: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\\s_-]", " ", query.lower())
    return " ".join(cleaned.split())


def _lookup_alias(query: str) -> Optional[dict]:
    key = _normalize_query_key(query)
    if key in LIVE_PLAYER_ALIASES:
        return LIVE_PLAYER_ALIASES[key]

    # Phrase containment fallback (e.g. "show me haaland xg trend").
    for alias_key, alias in LIVE_PLAYER_ALIASES.items():
        if f" {alias_key} " in f" {key} ":
            return alias

    # Surname fallback ("Erling Haaland" -> "haaland")
    tokens = [t for t in key.split(" ") if t]
    if tokens:
        return LIVE_PLAYER_ALIASES.get(tokens[-1])
    return None


def _alias_to_search_payload(alias: dict) -> dict:
    return {
        "results": [
            {
                "type": "player",
                "entity": {
                    "id": alias["athlete_id"],
                    "name": alias["name"],
                    "team": {"name": alias.get("team", "Unknown")},
                },
                "score": 100.0,
            }
        ]
    }


# ─── API Client ───────────────────────────────────────────────────────────────

async def _api_request(endpoint: str, params: dict = None) -> dict:
    """Make an authenticated request to SportsAPIPro direct API."""
    headers = {
        "x-api-key": API_KEY,
    }
    url = f"{API_BASE_URL}{endpoint}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()


# ─── Tool Functions ───────────────────────────────────────────────────────────

@dataclass
class ToolResult:
    """Standard return type for all data tools."""
    data: any
    cache_hit: bool = False
    ttl_remaining_s: Optional[int] = None
    warnings: list = field(default_factory=list)
    error: Optional[str] = None


async def search_entity(
    query: str,
    data_mode: str = "live",
    allow_live_fetch: bool = True,
) -> ToolResult:
    """
    Search for a player or team by name.

    Returns:
        ToolResult with data = list of entity matches
    """
    cache_key = f"{data_mode}:search_entity:{query.lower().strip()}"
    warnings = []

    # Check cache first
    cached = _cache.get(cache_key)
    if cached:
        if data_mode == "replay":
            warnings.append(_make_replay_warning(source="cache"))
        warnings.append({
            "code": "USED_CACHED_DATA",
            "message": f"Using cached search results for '{query}'.",
            "details": {"ttl_remaining_s": cached.ttl_remaining_s},
        })
        return ToolResult(
            data=cached.data,
            cache_hit=True,
            ttl_remaining_s=cached.ttl_remaining_s,
            warnings=warnings,
        )

    # Replay mode
    if data_mode == "replay":
        fixture_name = None
        fixture_data = None
        for candidate in _search_fixture_candidates(query):
            fixture_data = _load_fixture(candidate)
            if fixture_data is not None:
                fixture_name = candidate
                break

        if fixture_data is None:
            attempted = _search_fixture_candidates(query)
            return ToolResult(
                data=None,
                error=f"Replay fixture not found: {attempted[0] if attempted else query}",
                warnings=[{
                    "code": "DATA_MODE_REPLAY",
                    "message": f"Fixture missing for query '{query}'",
                    "details": {"attempted_fixtures": attempted, "source": "fixture"},
                }],
            )

        _cache.set(cache_key, fixture_data)
        return ToolResult(
            data=fixture_data,
            cache_hit=False,
            warnings=[_make_replay_warning(fixture=fixture_name, source="fixture")],
        )

    # Cache-only mode
    if not allow_live_fetch:
        return ToolResult(
            data=None,
            error="No cached data available and live fetch is disabled.",
            warnings=[{
                "code": "CACHE_ONLY_MODE",
                "message": "allow_live_fetch=false; no cached search results available.",
                "details": {},
            }],
        )

    # Live API call
    try:
        result = await _api_request("/search", params={"query": query, "filter": "athletes"})
        _cache.set(cache_key, result)
        return ToolResult(data=result, cache_hit=False)
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response is not None else None
        # Some plans block /search (404/403) or throttle it aggressively (429).
        # Fall back to a small alias map so live demos can still proceed.
        if status_code in (403, 404, 429):
            alias = _lookup_alias(query)
            if alias:
                payload = _alias_to_search_payload(alias)
                _cache.set(cache_key, payload)
                warnings.append({
                    "code": "SEARCH_UNAVAILABLE_USING_ALIAS",
                    "message": "Live search endpoint unavailable. Resolved player from local alias map.",
                    "details": {
                        "query": query,
                        "athlete_id": alias["athlete_id"],
                        "status_code": status_code,
                    },
                })
                return ToolResult(
                    data=payload,
                    cache_hit=False,
                    warnings=warnings,
                )

            return ToolResult(
                data=None,
                error=f"Live search endpoint unavailable (HTTP {status_code}) and no alias mapping found for '{query}'.",
                warnings=[{
                    "code": "SEARCH_ENDPOINT_UNAVAILABLE",
                    "message": "Live search endpoint is unavailable on current plan.",
                    "details": {"query": query, "status_code": status_code},
                }],
            )

        logger.error(f"search_entity API error: {e}")
        return ToolResult(data=None, error=str(e))
    except Exception as e:
        logger.error(f"search_entity API error: {e}")
        return ToolResult(data=None, error=str(e))


async def get_athlete_games(
    athlete_id: int,
    last_n: int = 5,
    data_mode: str = "live",
    allow_live_fetch: bool = True,
) -> ToolResult:
    """
    Fetch recent game summaries for an athlete (L1 data).

    Returns:
        ToolResult with data = dict containing games list,
        each game has extracted metrics keyed by metric.key
    """
    cache_key = f"{data_mode}:athlete_games:{athlete_id}:last{last_n}"
    warnings = []

    # Check cache
    cached = _cache.get(cache_key)
    if cached:
        if data_mode == "replay":
            warnings.append(_make_replay_warning(source="cache"))
        warnings.append({
            "code": "USED_CACHED_DATA",
            "message": f"Using cached game data for athlete {athlete_id}.",
            "details": {"ttl_remaining_s": cached.ttl_remaining_s},
        })
        return ToolResult(
            data=cached.data,
            cache_hit=True,
            ttl_remaining_s=cached.ttl_remaining_s,
            warnings=warnings,
        )

    # Replay mode
    if data_mode == "replay":
        fixture_name = f"athletes_games__{athlete_id}__last{last_n}.json"
        fixture_data = _load_fixture(fixture_name)
        if fixture_data is None:
            return ToolResult(
                data=None,
                error=f"Replay fixture not found: {fixture_name}",
                warnings=[{
                    "code": "DATA_MODE_REPLAY",
                    "message": f"Fixture missing: {fixture_name}",
                    "details": {"fixture": fixture_name, "source": "fixture"},
                }],
            )
        # Normalize fixture data
        normalized = _normalize_games(fixture_data)
        _cache.set(cache_key, normalized)
        return ToolResult(
            data=normalized,
            cache_hit=False,
            warnings=[_make_replay_warning(fixture=fixture_name, source="fixture")],
        )

    # Cache-only mode
    if not allow_live_fetch:
        return ToolResult(
            data=None,
            error="No cached data available and live fetch is disabled.",
            warnings=[{
                "code": "CACHE_ONLY_MODE",
                "message": "allow_live_fetch=false; no cached game data available.",
                "details": {},
            }],
        )

    # Live API call
    try:
        result = await _api_request(
            "/athletes/games",
            params={"athleteId": athlete_id, "numOfGames": last_n},
        )
        normalized = _normalize_games(result)
        _cache.set(cache_key, normalized)
        return ToolResult(data=normalized, cache_hit=False)
    except Exception as e:
        logger.error(f"get_athlete_games API error: {e}")
        return ToolResult(data=None, error=str(e))


async def get_game_lineup(
    athlete_id: int,
    game_id: int,
    data_mode: str = "live",
    allow_live_fetch: bool = True,
) -> ToolResult:
    """
    Fetch detailed lineup stats for a specific game (L2 data).

    Returns:
        ToolResult with data = dict of all extracted metrics (L1 + L2)
    """
    cache_key = f"{data_mode}:lineup:{athlete_id}:{game_id}"
    warnings = []

    # Check cache
    cached = _cache.get(cache_key)
    if cached:
        if data_mode == "replay":
            warnings.append(_make_replay_warning(source="cache"))
        warnings.append({
            "code": "USED_CACHED_DATA",
            "message": f"Using cached lineup data for game {game_id}.",
            "details": {"ttl_remaining_s": cached.ttl_remaining_s},
        })
        return ToolResult(
            data=cached.data,
            cache_hit=True,
            ttl_remaining_s=cached.ttl_remaining_s,
            warnings=warnings,
        )

    # Replay mode
    if data_mode == "replay":
        fixture_name = f"athlete_lineup__{athlete_id}__{game_id}.json"
        fixture_data = _load_fixture(fixture_name)
        if fixture_data is None:
            return ToolResult(
                data=None,
                error=f"Replay fixture not found: {fixture_name}",
                warnings=[{
                    "code": "DATA_MODE_REPLAY",
                    "message": f"Fixture missing: {fixture_name}",
                    "details": {"fixture": fixture_name, "source": "fixture"},
                }],
            )
        normalized = _normalize_lineup(fixture_data)
        _cache.set(cache_key, normalized)
        return ToolResult(
            data=normalized,
            cache_hit=False,
            warnings=[_make_replay_warning(fixture=fixture_name, source="fixture")],
        )

    # Cache-only mode
    if not allow_live_fetch:
        return ToolResult(
            data=None,
            error="No cached data available and live fetch is disabled.",
            warnings=[{
                "code": "CACHE_ONLY_MODE",
                "message": "allow_live_fetch=false; no cached lineup data available.",
                "details": {},
            }],
        )

    # Live API call
    try:
        result = await _api_request(
            "/athletes/games/lineups",
            params={"athleteId": athlete_id, "gameId": game_id},
        )
        normalized = _normalize_lineup(result)
        _cache.set(cache_key, normalized)
        return ToolResult(data=normalized, cache_hit=False)
    except Exception as e:
        logger.error(f"get_game_lineup API error: {e}")
        return ToolResult(data=None, error=str(e))


# ─── Normalization (raw API → structured metrics) ────────────────────────────

def _normalize_games(raw: dict) -> dict:
    """
    Normalize raw API response into structured game data with extracted metrics.
    Uses L1 metrics only (per STATS_CONFIG).

    Returns:
        {
            "games": [
                {
                    "game_id": int,
                    "date": str,
                    "opponent": str,
                    "score": str,
                    "metrics": {"goals": 2, "assists": 0, "minutes_played": 90, ...},
                    "unknown_type_ids": [999, ...]  # for NORMALIZATION_GAP
                },
                ...
            ],
            "normalization_warnings": [...]
        }
    """
    games_out = []
    norm_warnings = []

    for game in raw.get("games", []):
        stats = _extract_stats_list(game)
        metrics = {}
        unknown_ids = []
        game_id = _extract_game_id(game)

        # Extract known metrics
        for metric_def in L1_METRICS:
            val = _extract_metric_value_with_fallback(stats, metric_def)
            metrics[metric_def.key] = val

        # Detect unknown type IDs (NORMALIZATION_GAP)
        known_ids = set()
        for metric in ALL_RAW_METRICS:
            if metric.api_type_id is not None:
                known_ids.add(metric.api_type_id)
            known_ids.update(LIVE_TYPE_ID_FALLBACKS.get(metric.key, ()))
        for stat in stats:
            if not isinstance(stat, dict):
                continue
            type_id = stat.get("type")
            if type_id is None:
                continue
            if type_id not in known_ids:
                unknown_ids.append(type_id)

        if unknown_ids:
            norm_warnings.append({
                "code": "NORMALIZATION_GAP",
                "message": f"Unknown stat type IDs encountered in game {game_id}: {unknown_ids}",
                "details": {"game_id": game_id, "unknown_type_ids": unknown_ids},
            })

        games_out.append({
            "game_id": game_id,
            "date": _extract_game_date(game),
            "opponent": _derive_opponent(game),
            "score": _extract_game_score(game),
            "metrics": metrics,
            "unknown_type_ids": unknown_ids,
        })

    return {
        "games": games_out,
        "normalization_warnings": norm_warnings,
    }


def _normalize_lineup(raw: dict) -> dict:
    """
    Normalize raw lineup response with L1 + L2 metrics.

    Returns:
        {
            "game_id": int,
            "athlete_id": int,
            "position": str,
            "metrics": {"goals": 2, "xg": 1.35, ...},
            "unknown_type_ids": [...],
            "normalization_warnings": [...]
        }
    """
    lineup = raw.get("lineup", raw if isinstance(raw, dict) else {})
    stats = _extract_stats_list(lineup)
    metrics = {}
    unknown_ids = []
    norm_warnings = []

    # Extract ALL metrics (L1 + L2)
    for metric_def in ALL_RAW_METRICS:
        val = _extract_metric_value_with_fallback(stats, metric_def)
        metrics[metric_def.key] = val

    # Detect unknown IDs
    known_ids = set()
    for metric in ALL_RAW_METRICS:
        if metric.api_type_id is not None:
            known_ids.add(metric.api_type_id)
        known_ids.update(LIVE_TYPE_ID_FALLBACKS.get(metric.key, ()))
    for stat in stats:
        if not isinstance(stat, dict):
            continue
        type_id = stat.get("type")
        if type_id is None:
            continue
        if type_id not in known_ids:
            unknown_ids.append(type_id)
            norm_warnings.append({
                "code": "NORMALIZATION_GAP",
                "message": f"Unknown stat type ID: {type_id}",
                "details": {"unknown_type_id": type_id},
            })

    return {
        "game_id": _extract_game_id(lineup),
        "athlete_id": lineup.get("athlete_id") or lineup.get("athleteId"),
        "position": _extract_position(lineup),
        "metrics": metrics,
        "unknown_type_ids": unknown_ids,
        "normalization_warnings": norm_warnings,
    }


def _derive_opponent(game: dict) -> str:
    """Best-effort opponent derivation from home/away fields."""
    game_obj = game.get("game", game) if isinstance(game, dict) else {}

    home = game.get("home_team", "") if isinstance(game, dict) else ""
    away = game.get("away_team", "") if isinstance(game, dict) else ""
    if not home and isinstance(game_obj, dict):
        home = (game_obj.get("homeCompetitor") or {}).get("name", "")
    if not away and isinstance(game_obj, dict):
        away = (game_obj.get("awayCompetitor") or {}).get("name", "")

    related_competitor = game.get("relatedCompetitor") if isinstance(game, dict) else None
    if related_competitor is not None and isinstance(game_obj, dict):
        home_comp = game_obj.get("homeCompetitor") or {}
        away_comp = game_obj.get("awayCompetitor") or {}
        home_id = home_comp.get("id")
        away_id = away_comp.get("id")
        if home_id == related_competitor:
            return away_comp.get("name") or away or "Unknown"
        if away_id == related_competitor:
            return home_comp.get("name") or home or "Unknown"

    if home and away:
        return f"{home} vs {away}"
    return home or away or "Unknown"


def _extract_position(lineup: dict) -> Optional[str]:
    position = lineup.get("position")
    if isinstance(position, dict):
        return position.get("name")
    return position


def _extract_game_id(game: dict) -> Optional[int]:
    if not isinstance(game, dict):
        return None
    if game.get("game_id") is not None:
        return game.get("game_id")
    game_obj = game.get("game", {})
    if isinstance(game_obj, dict):
        return game_obj.get("id")
    return game.get("id")


def _extract_game_date(game: dict) -> Optional[str]:
    if not isinstance(game, dict):
        return None
    if game.get("date"):
        return game.get("date")
    game_obj = game.get("game", {})
    if isinstance(game_obj, dict):
        return game_obj.get("startTime")
    return game.get("startTime")


def _extract_game_score(game: dict) -> Optional[str]:
    if not isinstance(game, dict):
        return None
    if game.get("score"):
        return game.get("score")
    game_obj = game.get("game", {})
    if not isinstance(game_obj, dict):
        return None
    home = (game_obj.get("homeCompetitor") or {}).get("score")
    away = (game_obj.get("awayCompetitor") or {}).get("score")
    if home is not None and away is not None:
        return f"{home}-{away}"
    scores = game_obj.get("scores")
    if isinstance(scores, list) and len(scores) >= 2:
        return f"{scores[0]}-{scores[1]}"
    return None


def _extract_stats_list(record: dict) -> list:
    if not isinstance(record, dict):
        return []
    stats = record.get("statistics")
    if isinstance(stats, list) and stats:
        return stats

    # New live shape can be wrapped: {"game": {...}, "athleteStats": [...]}
    athlete_stats = record.get("athleteStats")
    if isinstance(athlete_stats, list) and athlete_stats:
        return athlete_stats

    wrapped = record.get("lineup", {})
    if isinstance(wrapped, dict):
        stats = wrapped.get("statistics")
        if isinstance(stats, list) and stats:
            return stats
        athlete_stats = wrapped.get("athleteStats")
        if isinstance(athlete_stats, list) and athlete_stats:
            return athlete_stats
    return []


def _extract_metric_value_with_fallback(statistics: list[dict], metric: MetricDef):
    if metric.api_type_id is None:
        return None

    candidate_type_ids = (metric.api_type_id,) + LIVE_TYPE_ID_FALLBACKS.get(metric.key, ())
    for type_id in candidate_type_ids:
        found, value = _find_stat_value(statistics, type_id)
        if not found:
            continue
        if value is None:
            if metric.missing_semantic == MissingSemantic.TRUE_ZERO:
                return 0
            return None
        return value

    if metric.missing_semantic == MissingSemantic.TRUE_ZERO:
        return 0
    return None


def _find_stat_value(statistics: list[dict], type_id: int) -> tuple[bool, Optional[float]]:
    for stat in statistics:
        if not isinstance(stat, dict):
            continue
        if stat.get("type") != type_id:
            continue
        return True, _coerce_numeric(stat.get("value"))
    return False, None


def _coerce_numeric(value):
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            if "." in stripped:
                return float(stripped)
            return int(stripped)
        except ValueError:
            return None
    return value


# ─── Cache Management (for external use) ─────────────────────────────────────

def get_cache() -> TTLCache:
    """Return the global cache instance."""
    return _cache


def clear_cache():
    """Clear all cached data."""
    _cache.clear()
