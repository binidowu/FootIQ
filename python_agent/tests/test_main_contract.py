"""
Contract-envelope tests for main.py endpoint wiring.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from football_agent import ContractError
from main import app


def _valid_request_body():
    return {
        "schema_version": "1.1",
        "trace_id": "ftiq_test_20260211_120000",
        "session": {
            "session_id": "sess_test",
            "history": [],
            "memory_summary": None,
        },
        "query": "How is Haaland doing?",
        "constraints": {
            "data_mode": "replay",
            "max_depth": "auto",
            "allow_live_fetch": True,
        },
    }


def test_main_success_envelope_and_suggestion_cap():
    client = TestClient(app)

    agent_result = SimpleNamespace(
        answer="Haaland is in strong form.",
        artifacts=[],
        sources=[],
        data_depth="L1",
        reasoning_mode="DATA_ONLY",
        tools_invoked=[{"tool": "search_player", "duration_ms": 10, "cache_hit": True}],
        warnings=[{"code": "DATA_MODE_REPLAY", "message": "Replay mode", "details": {}}],
        suggestions=["a", "b", "c", "d", "e"],
        updated_summary="User asked about Haaland.",
    )

    with patch("football_agent.run_agent", new=AsyncMock(return_value=agent_result)):
        response = client.post("/agent/query", json=_valid_request_body())

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["error"] is None
    assert isinstance(payload["warnings"], list)
    assert isinstance(payload["suggestions"], list)
    assert len(payload["suggestions"]) <= 3
    assert "schema_version" in payload
    assert "trace_id" in payload
    assert "output" in payload and "answer" in payload["output"]
    assert "metadata" in payload and "tools_invoked" in payload["metadata"]


def test_main_error_envelope_contract_fields():
    client = TestClient(app)

    with patch(
        "football_agent.run_agent",
        new=AsyncMock(side_effect=ContractError("PLAYER_NOT_FOUND", "No player found.", options=[])),
    ):
        response = client.post("/agent/query", json=_valid_request_body())

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "PLAYER_NOT_FOUND"
    assert isinstance(payload["warnings"], list)
    assert isinstance(payload["suggestions"], list)
    assert payload["error"] is not None
    assert "metadata" in payload and "tools_invoked" in payload["metadata"]


def test_main_upstream_down_error_is_sanitized():
    client = TestClient(app)

    raw = (
        "Client error '401 Unauthorized' for url "
        "'https://sportapi7.p.rapidapi.com/api/v1/search?q=Mohamed%20Salah'"
    )
    with patch(
        "football_agent.run_agent",
        new=AsyncMock(side_effect=ContractError("UPSTREAM_DOWN", raw)),
    ):
        response = client.post("/agent/query", json=_valid_request_body())

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "UPSTREAM_DOWN"
    assert payload["error"]["message"] == "Live data source is unavailable right now. Try replay mode or retry later."
    assert "http" not in payload["error"]["message"].lower()
    assert "unauthorized" not in payload["error"]["message"].lower()


def test_main_unhandled_error_returns_safe_message():
    client = TestClient(app)

    with patch(
        "football_agent.run_agent",
        new=AsyncMock(side_effect=RuntimeError("boom: https://internal.local/token")),
    ):
        response = client.post("/agent/query", json=_valid_request_body())

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "UPSTREAM_DOWN"
    assert payload["error"]["message"] == "The analysis service is temporarily unavailable. Please try again shortly."
