"""
FootIQ Agent (Phase 4)

Deterministic routing + constrained tool-calling agent layer.
This module maps user intent to tool availability and returns contract-friendly
results for main.py response builders.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from data_tools import get_athlete_games, get_game_lineup, search_entity
from quant_tools import compute_derived, compute_form, compute_per90, compute_zscore, generate_plot

logger = logging.getLogger("footiq.agent")

MAX_TOOL_CALL_ITERATIONS = int(os.getenv("AGENT_MAX_TOOL_ITERATIONS", "5"))


# ─── Contract Exceptions ──────────────────────────────────────────────────────

class ContractError(Exception):
    """Base exception mapped to API_CONTRACT error codes."""

    def __init__(self, code: str, message: str, options: Optional[list] = None):
        self.code = code
        self.message = message
        self.options = options or []
        super().__init__(message)


class PlayerNotFoundError(ContractError):
    def __init__(self, query: str):
        super().__init__("PLAYER_NOT_FOUND", f"No player found matching '{query}'.")


class AmbiguousEntityError(ContractError):
    def __init__(self, query: str, options: list):
        super().__init__("AMBIGUOUS_ENTITY", f"Multiple matches found for '{query}'.", options=options)


class InsufficientContextError(ContractError):
    def __init__(self):
        super().__init__(
            "INSUFFICIENT_CONTEXT",
            "Please specify who you are asking about (e.g., 'How is Saka doing?').",
        )


class InsufficientDataError(ContractError):
    def __init__(self, player_id: int):
        super().__init__("INSUFFICIENT_DATA", f"No recent games found for player {player_id}.")


# ─── Agent Result ─────────────────────────────────────────────────────────────

@dataclass
class AgentResult:
    answer: str
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[Dict[str, Any]] = field(default_factory=list)
    data_depth: str = "L1"
    reasoning_mode: str = "DATA_ONLY"
    tools_invoked: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    updated_summary: str = ""
    error: Optional[Dict[str, Any]] = None


# ─── Per-request Context ──────────────────────────────────────────────────────

_request_context: Dict[str, Any] = {}


def set_request_context(data_mode: str, allow_live_fetch: bool) -> None:
    global _request_context
    _request_context = {
        "data_mode": data_mode,
        "allow_live_fetch": allow_live_fetch,
        "warnings": [],
        "artifacts": [],
        "sources": [],
        "last_cache_hit": None,
    }


def _append_warnings(warnings: Optional[list]) -> None:
    if not warnings:
        return
    _request_context.setdefault("warnings", []).extend(warnings)


def _normalize_search_results(payload: Any) -> List[dict]:
    """
    Normalize search payload into a flat list:
    [{"id": int, "name": str, "team": str, "score": float}, ...]
    """
    if isinstance(payload, dict):
        rows = payload.get("results", [])
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []

    out: List[dict] = []
    for row in rows:
        if isinstance(row, dict) and "entity" in row:
            entity = row.get("entity", {})
            team = entity.get("team", {}) if isinstance(entity.get("team"), dict) else {}
            out.append(
                {
                    "id": entity.get("id"),
                    "name": entity.get("name"),
                    "team": team.get("name"),
                    "score": row.get("score"),
                    "position": entity.get("position"),
                }
            )
        elif isinstance(row, dict):
            out.append(
                {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "team": row.get("team"),
                    "score": row.get("score"),
                    "position": row.get("position"),
                }
            )
    return [r for r in out if r.get("id") is not None and r.get("name")]


# ─── Tool Wrappers ────────────────────────────────────────────────────────────

@tool
async def search_player(query: str) -> dict:
    """Search for a football player by name and return a resolved player record."""
    mode = _request_context.get("data_mode", "live")
    allow_live_fetch = _request_context.get("allow_live_fetch", True)

    result = await search_entity(query, data_mode=mode, allow_live_fetch=allow_live_fetch)
    _append_warnings(result.warnings)
    _request_context["last_cache_hit"] = result.cache_hit

    if result.error:
        raise ContractError("UPSTREAM_DOWN", result.error)

    matches = _normalize_search_results(result.data)
    if not matches:
        raise PlayerNotFoundError(query)

    if len(matches) > 1:
        exact = [m for m in matches if str(m["name"]).lower() == query.lower()]
        if len(exact) == 1:
            return exact[0]
        options = [
            {"label": f"{m['name']} ({m.get('team') or '?'})", "athlete_id": m["id"]}
            for m in matches[:5]
        ]
        raise AmbiguousEntityError(query, options)

    return matches[0]


@tool
async def get_recent_games(athlete_id: int, last_n: int = 5) -> list:
    """Get the last N normalized games for a player."""
    mode = _request_context.get("data_mode", "live")
    allow_live_fetch = _request_context.get("allow_live_fetch", True)

    result = await get_athlete_games(
        athlete_id,
        last_n=last_n,
        data_mode=mode,
        allow_live_fetch=allow_live_fetch,
    )
    _append_warnings(result.warnings)
    _request_context["last_cache_hit"] = result.cache_hit

    if result.error:
        raise ContractError("UPSTREAM_DOWN", result.error)

    payload = result.data or {}
    games = payload.get("games", []) if isinstance(payload, dict) else payload
    if not games:
        raise InsufficientDataError(athlete_id)

    if len(games) < 3:
        _append_warnings(
            [
                {
                    "code": "INSUFFICIENT_GAMES",
                    "message": f"Only {len(games)} games available in the requested window.",
                    "details": {"games_found": len(games), "threshold": 3},
                }
            ]
        )

    if isinstance(payload, dict):
        _append_warnings(payload.get("normalization_warnings", []))
    return games


@tool
async def get_detailed_stats(athlete_id: int, game_id: int) -> dict:
    """Get detailed lineup stats (L2) for a specific game."""
    mode = _request_context.get("data_mode", "live")
    allow_live_fetch = _request_context.get("allow_live_fetch", True)

    result = await get_game_lineup(
        athlete_id,
        game_id,
        data_mode=mode,
        allow_live_fetch=allow_live_fetch,
    )
    _append_warnings(result.warnings)
    _request_context["last_cache_hit"] = result.cache_hit

    if result.error:
        raise ContractError("UPSTREAM_DOWN", result.error)

    payload = result.data or {}
    if isinstance(payload, dict):
        _append_warnings(payload.get("normalization_warnings", []))
        return payload
    return {}


@tool
def calculate_per90(games: list, metric: str) -> float:
    """Compute per-90 rate for a metric (returns -1.0 when unavailable)."""
    res = compute_per90(games, metric)
    _append_warnings(res.warnings)
    if res.error or res.value is None:
        return -1.0
    return float(res.value)


@tool
def calculate_derived(games: list, metric: str) -> float:
    """Compute derived metric value (returns -1.0 when unavailable)."""
    res = compute_derived(games, metric)
    _append_warnings(res.warnings)
    if res.error or res.value is None:
        return -1.0
    return float(res.value)


@tool
def compare_to_league(
    per90_value: float,
    metric: str,
    league: str = "premier_league",
    season: str = "2025_2026",
    position: str = "all_positions",
) -> float:
    """Compute z-score against league average (returns raw value or 0.0 on error)."""
    if per90_value < 0:
        return 0.0

    res = compute_zscore(
        per90_value,
        metric,
        league=league,
        season=season,
        position=position,
    )
    _append_warnings(res.warnings)
    if res.error or res.value is None:
        return 0.0
    return float(res.value)


@tool
def show_form_chart(games: list, metric: str, player_name: str, trace_id: str) -> str:
    """Generate a trend chart URL for a metric."""
    form_res = compute_form(games, metric)
    _append_warnings(form_res.warnings)
    if not form_res.raw_values:
        return "No data for plot."

    labels = [g.get("date", f"G{i+1}") for i, g in enumerate(games[: len(form_res.raw_values)])]
    plot_res = generate_plot(form_res.raw_values, player_name, metric, trace_id, game_labels=labels)
    _append_warnings(plot_res.warnings)
    if plot_res.error or not plot_res.value:
        return "Plot generation failed."

    _request_context.setdefault("artifacts", []).append(
        {
            "type": "plot",
            "url": plot_res.value,
            "label": f"{metric.replace('_', ' ').title()} Form",
        }
    )
    return str(plot_res.value)


# ─── Router & Selector ────────────────────────────────────────────────────────

class Intent:
    SURFACE = "Surface"
    DEEP = "Deep"
    COMPARE = "Compare"


def route_intent(query: str, history: list) -> str:
    """Determine intent from query pattern + history context."""
    q = query.lower()

    if not history and any(w in q.split() for w in ["he", "she", "they", "him", "her"]):
        return "INSUFFICIENT_CONTEXT"

    if "compare" in q or " vs " in q or "better than" in q:
        return Intent.COMPARE

    if any(w in q for w in ["why", "analyze", "xg", "shot", "heatmap", "tactical", "declin", "improv"]):
        return Intent.DEEP

    return Intent.SURFACE


def select_tools(intent: str, max_depth: str) -> list:
    """Return allowed tools based on intent and constraints."""
    base = [search_player, get_recent_games, calculate_per90, compare_to_league]

    if max_depth == "L1":
        return base

    if intent == Intent.DEEP:
        return base + [get_detailed_stats, calculate_derived, show_form_chart]
    return base


# ─── Main Executor (LCEL Loop) ────────────────────────────────────────────────

async def run_agent(
    query: str,
    session_id: str,
    trace_id: str,
    history: list,
    memory_summary: str = None,
    data_mode: str = "live",
    max_depth: str = "auto",
    allow_live_fetch: bool = True,
) -> AgentResult:
    """
    Main entry point for the football agent.
    Uses explicit tool-calling loop for robust control and deterministic toolset.
    """
    set_request_context(data_mode, allow_live_fetch)

    intent = route_intent(query, history)
    if intent == "INSUFFICIENT_CONTEXT":
        raise InsufficientContextError()

    tools = select_tools(intent, max_depth)
    tool_map = {t.name: t for t in tools}

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ContractError("UPSTREAM_DOWN", "OPENAI_API_KEY is not configured.")

    system_text = (
        "You are a football analyst assistant. Use only the provided tools for factual stats. "
        "Keep answers concise and data-backed. "
        f"Intent={intent}. Trace ID={trace_id}. "
        "If a chart is generated, mention it briefly."
    )

    messages: List[Any] = [SystemMessage(content=system_text)]
    for msg in history:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=query))

    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0,
        api_key=api_key,
    )
    llm_with_tools = llm.bind_tools(tools)

    tools_invoked_log: List[dict] = []

    try:
        response = await llm_with_tools.ainvoke(messages)
    except Exception:
        logger.exception("LLM invocation failed")
        raise ContractError("UPSTREAM_TIMEOUT", "LLM service unavailable")

    messages.append(response)

    for _ in range(MAX_TOOL_CALL_ITERATIONS):
        if not response.tool_calls:
            break

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]

            tool_obj = tool_map.get(tool_name)
            if not tool_obj:
                messages.append(ToolMessage(tool_call_id=tool_id, content="Error: Tool not allowed"))
                continue

            started = time.perf_counter()
            try:
                tool_output = await tool_obj.ainvoke(tool_args)
            except ContractError:
                raise
            except Exception as exc:
                raise ContractError("UPSTREAM_DOWN", f"Tool {tool_name} failed: {exc}")

            duration_ms = int((time.perf_counter() - started) * 1000)
            tools_invoked_log.append(
                {
                    "tool": tool_name,
                    "duration_ms": duration_ms,
                    "cache_hit": _request_context.pop("last_cache_hit", None),
                }
            )

            if isinstance(tool_output, (dict, list)):
                content = json.dumps(tool_output)
            else:
                content = str(tool_output)
            messages.append(ToolMessage(tool_call_id=tool_id, content=content))

        try:
            response = await llm_with_tools.ainvoke(messages)
            messages.append(response)
        except Exception:
            raise ContractError("UPSTREAM_TIMEOUT", "LLM service unavailable")

    if response.tool_calls:
        raise ContractError(
            "UPSTREAM_TIMEOUT",
            f"Agent exceeded max tool iterations ({MAX_TOOL_CALL_ITERATIONS}).",
        )

    depth_used = "L2" if intent == Intent.DEEP and max_depth != "L1" else "L1"
    reasoning = "SYNTHESIS" if depth_used == "L2" else "DATA_ONLY"

    answer = response.content if isinstance(response.content, str) else str(response.content)
    suggestions = _request_context.get("suggestions", [])[:3]
    warnings = _request_context.get("warnings", [])

    return AgentResult(
        answer=answer,
        artifacts=_request_context.get("artifacts", []),
        sources=_request_context.get("sources", []),
        data_depth=depth_used,
        reasoning_mode=reasoning,
        tools_invoked=tools_invoked_log,
        warnings=warnings,
        suggestions=suggestions,
        updated_summary=f"User asked: {query[:250]}",
    )
