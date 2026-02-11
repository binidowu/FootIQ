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

API_BASE_URL = os.getenv("SPORTAPI_BASE_URL", "https://sportapi7.p.rapidapi.com/api/v1")
API_KEY = os.getenv("SPORTAPI_KEY", "")
API_HOST = os.getenv("SPORTAPI_HOST", "sportapi7.p.rapidapi.com")

FIXTURE_DIR = Path(__file__).parent / "tests" / "fixtures" / "sportapi"
CACHE_TTL_S = int(os.getenv("CACHE_TTL_S", "1800"))  # 30 minutes default


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


# ─── API Client ───────────────────────────────────────────────────────────────

async def _api_request(endpoint: str, params: dict = None) -> dict:
    """Make an authenticated request to SportsAPIPro."""
    headers = {
        "X-RapidAPI-Key": API_KEY,
        "X-RapidAPI-Host": API_HOST,
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
    cache_key = f"search_entity:{query.lower().strip()}"
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
        result = await _api_request("/search", params={"q": query})
        _cache.set(cache_key, result)
        return ToolResult(data=result, cache_hit=False)
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
    cache_key = f"athlete_games:{athlete_id}:last{last_n}"
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
            f"/athletes/{athlete_id}/games",
            params={"limit": last_n},
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
    cache_key = f"lineup:{athlete_id}:{game_id}"
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
            f"/games/{game_id}/lineups",
            params={"athlete_id": athlete_id},
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
        stats = game.get("statistics", [])
        metrics = {}
        unknown_ids = []

        # Extract known metrics
        for metric_def in L1_METRICS:
            val = extract_metric_value(stats, metric_def)
            metrics[metric_def.key] = val

        # Detect unknown type IDs (NORMALIZATION_GAP)
        known_ids = {m.api_type_id for m in ALL_RAW_METRICS if m.api_type_id is not None}
        for stat in stats:
            type_id = stat.get("type")
            if type_id not in known_ids:
                unknown_ids.append(type_id)

        if unknown_ids:
            norm_warnings.append({
                "code": "NORMALIZATION_GAP",
                "message": f"Unknown stat type IDs encountered in game {game.get('game_id')}: {unknown_ids}",
                "details": {"game_id": game.get("game_id"), "unknown_type_ids": unknown_ids},
            })

        games_out.append({
            "game_id": game.get("game_id"),
            "date": game.get("date"),
            "opponent": _derive_opponent(game),
            "score": game.get("score"),
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
    lineup = raw.get("lineup", {})
    stats = lineup.get("statistics", [])
    metrics = {}
    unknown_ids = []
    norm_warnings = []

    # Extract ALL metrics (L1 + L2)
    for metric_def in ALL_RAW_METRICS:
        val = extract_metric_value(stats, metric_def)
        metrics[metric_def.key] = val

    # Detect unknown IDs
    known_ids = {m.api_type_id for m in ALL_RAW_METRICS if m.api_type_id is not None}
    for stat in stats:
        type_id = stat.get("type")
        if type_id not in known_ids:
            unknown_ids.append(type_id)
            norm_warnings.append({
                "code": "NORMALIZATION_GAP",
                "message": f"Unknown stat type ID: {type_id}",
                "details": {"unknown_type_id": type_id},
            })

    return {
        "game_id": lineup.get("game_id"),
        "athlete_id": lineup.get("athlete_id"),
        "position": lineup.get("position"),
        "metrics": metrics,
        "unknown_type_ids": unknown_ids,
        "normalization_warnings": norm_warnings,
    }


def _derive_opponent(game: dict) -> str:
    """Best-effort opponent derivation from home/away fields."""
    home = game.get("home_team", "")
    away = game.get("away_team", "")
    if home and away:
        return f"{home} vs {away}"
    return home or away or "Unknown"


# ─── Cache Management (for external use) ─────────────────────────────────────

def get_cache() -> TTLCache:
    """Return the global cache instance."""
    return _cache


def clear_cache():
    """Clear all cached data."""
    _cache.clear()
