"""
FootIQ Agent Tests — Offline / Mocked

Verifies routing, tool selection, loop safety, and contract error mapping
without making real LLM calls.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from football_agent import (
    ContractError,
    Intent,
    route_intent,
    run_agent,
    search_player,
    select_tools,
)


@pytest.fixture(autouse=True)
def set_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


# ─── Routing Tests ────────────────────────────────────────────────────────────

def test_route_intent_surface():
    assert route_intent("How is Haaland doing?", []) == Intent.SURFACE
    assert route_intent("Saka stats", []) == Intent.SURFACE


def test_route_intent_deep():
    assert route_intent("Why is he declining?", [{"role": "user", "content": "..."}]) == Intent.DEEP
    assert route_intent("Analyze xG performance", []) == Intent.DEEP
    assert route_intent("Show me a shot map", []) == Intent.DEEP


def test_route_intent_compare():
    assert route_intent("Compare Saka and Foden", []) == Intent.COMPARE
    assert route_intent("Who is better vs Palmer", []) == Intent.COMPARE


def test_route_intent_insufficient_context():
    assert route_intent("How is he doing?", []) == "INSUFFICIENT_CONTEXT"
    assert route_intent("How is he doing?", [{"role": "user", "content": "Raya"}]) == Intent.SURFACE


# ─── Tool Selection Tests ─────────────────────────────────────────────────────

def test_select_tools_surface():
    tools = select_tools(Intent.SURFACE, "auto")
    names = [t.name for t in tools]
    assert "search_player" in names
    assert "get_recent_games" in names
    assert "get_detailed_stats" not in names


def test_select_tools_deep():
    tools = select_tools(Intent.DEEP, "auto")
    names = [t.name for t in tools]
    assert "get_detailed_stats" in names
    assert "show_form_chart" in names
    assert "calculate_derived" in names


def test_select_tools_l1_constraint():
    tools = select_tools(Intent.DEEP, "L1")
    names = [t.name for t in tools]
    assert "get_detailed_stats" not in names
    assert "show_form_chart" not in names
    assert "calculate_derived" not in names
    assert "search_player" in names


# ─── Agent Execution & Error Mapping Tests ────────────────────────────────────

@pytest.fixture
def mock_llm_chain():
    with patch("football_agent.ChatOpenAI") as llm_cls:
        mock_llm = llm_cls.return_value
        chain = MagicMock()
        mock_llm.bind_tools.return_value = chain
        chain.ainvoke = AsyncMock(return_value=AIMessage(content="Haaland is doing great."))
        yield chain


@pytest.mark.asyncio
async def test_run_agent_success(mock_llm_chain):
    result = await run_agent(
        query="How is Haaland?",
        session_id="sess_1",
        trace_id="trace_1",
        history=[],
    )
    assert result.answer == "Haaland is doing great."
    assert result.data_depth == "L1"
    assert isinstance(result.tools_invoked, list)
    assert isinstance(result.warnings, list)


@pytest.mark.asyncio
async def test_run_agent_insufficient_context_error():
    with pytest.raises(ContractError) as excinfo:
        await run_agent(query="How is he doing?", session_id="1", trace_id="1", history=[])
    assert excinfo.value.code == "INSUFFICIENT_CONTEXT"


@pytest.mark.asyncio
async def test_run_agent_player_not_found(mock_llm_chain):
    mock_llm_chain.ainvoke.side_effect = [
        AIMessage(
            content="",
            tool_calls=[{"name": "search_player", "args": {"query": "Unknown"}, "id": "call_1"}],
        ),
    ]
    with patch("football_agent.search_entity", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = SimpleNamespace(data={"results": []}, error=None, warnings=[], cache_hit=False)
        with pytest.raises(ContractError) as excinfo:
            await run_agent(query="Who is Unknown?", session_id="1", trace_id="1", history=[])
        assert excinfo.value.code == "PLAYER_NOT_FOUND"


@pytest.mark.asyncio
async def test_run_agent_internal_error_llm():
    with patch("football_agent.ChatOpenAI") as llm_cls:
        chain = llm_cls.return_value.bind_tools.return_value
        chain.ainvoke.side_effect = Exception("OpenAI down")
        with pytest.raises(ContractError) as excinfo:
            await run_agent(query="Hi", session_id="1", trace_id="1", history=[])
        assert excinfo.value.code == "UPSTREAM_TIMEOUT"


@pytest.mark.asyncio
async def test_run_agent_missing_openai_api_key_maps_upstream_down(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ContractError) as excinfo:
        await run_agent(query="How is Haaland?", session_id="1", trace_id="1", history=[])
    assert excinfo.value.code == "UPSTREAM_DOWN"


@pytest.mark.asyncio
async def test_run_agent_tool_loop_iteration_cap(mock_llm_chain):
    # Perpetual tool-calling response should trip loop cap.
    repeated = AIMessage(
        content="",
        tool_calls=[{"name": "unknown_tool", "args": {}, "id": "call_x"}],
    )
    mock_llm_chain.ainvoke.side_effect = [repeated, repeated, repeated, repeated, repeated, repeated]

    with pytest.raises(ContractError) as excinfo:
        await run_agent(query="How is Haaland?", session_id="1", trace_id="trace_1", history=[])
    assert excinfo.value.code == "UPSTREAM_TIMEOUT"
    assert "max tool iterations" in excinfo.value.message.lower()


@pytest.mark.asyncio
async def test_run_agent_replay_warning_propagates(mock_llm_chain):
    mock_llm_chain.ainvoke.side_effect = [
        AIMessage(
            content="",
            tool_calls=[{"name": "search_player", "args": {"query": "haaland"}, "id": "call_1"}],
        ),
        AIMessage(content="Done."),
    ]

    with patch("football_agent.search_entity", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = SimpleNamespace(
            data={
                "results": [
                    {
                        "entity": {"id": 939180, "name": "Erling Haaland", "team": {"name": "Manchester City"}},
                        "score": 98.5,
                    }
                ]
            },
            error=None,
            warnings=[{"code": "DATA_MODE_REPLAY", "message": "Replay", "details": {"source": "cache"}}],
            cache_hit=True,
        )
        result = await run_agent(
            query="How is Haaland doing?",
            session_id="1",
            trace_id="trace_1",
            history=[],
            data_mode="replay",
        )

    warning_codes = [w["code"] for w in result.warnings]
    assert "DATA_MODE_REPLAY" in warning_codes


# ─── Tool Wrapper Logic Test ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_player_ambiguous():
    from football_agent import set_request_context

    set_request_context("live", True)
    with patch("football_agent.search_entity", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = SimpleNamespace(
            data={
                "results": [
                    {
                        "entity": {"id": 1, "name": "Bukayo Saka", "team": {"name": "Arsenal"}},
                        "score": 96.2,
                    },
                    {
                        "entity": {"id": 2, "name": "Yaya Saka", "team": {"name": "Strasbourg"}},
                        "score": 41.0,
                    },
                ]
            },
            error=None,
            warnings=[],
            cache_hit=False,
        )

        with pytest.raises(ContractError) as exc:
            await search_player.ainvoke({"query": "Saka"})

        assert exc.value.code == "AMBIGUOUS_ENTITY"
        assert len(exc.value.options) == 2
