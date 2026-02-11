"""
FootIQ Python Agent Service — Shell (Phase 1)

Validates incoming requests per API_CONTRACT.md §1.3 and returns
a mock response using the contract schema (§2.1/§2.2).

Replace the mock logic with real tool chains in Phase 2–4.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
import time
import os

app = FastAPI(title="FootIQ Agent", version="1.1")

SCHEMA_VERSION = "1.1"
DATA_MODE = os.getenv("DATA_MODE", "live")
MAX_HISTORY = 10


# ─── Request Validation Models ───────────────────────────────────────────────

class SessionInput(BaseModel):
    session_id: str
    history: list = Field(default_factory=list)
    memory_summary: Optional[str] = None


class Constraints(BaseModel):
    data_mode: str = "live"
    max_depth: str = "auto"
    allow_live_fetch: bool = True


class QueryRequest(BaseModel):
    schema_version: str
    trace_id: str
    session: SessionInput
    query: str
    constraints: Constraints = Field(default_factory=Constraints)


# ─── Response Helpers ─────────────────────────────────────────────────────────

def make_error_response(trace_id: str, session_id: str, code: str, message: str,
                        options: list = None, retry_after_s: int = None,
                        warnings: list = None, suggestions: list = None,
                        updated_summary: str = None):
    """Build a contract-compliant error envelope."""
    return {
        "schema_version": SCHEMA_VERSION,
        "trace_id": trace_id,
        "status": "error",
        "session": {
            "session_id": session_id,
            "updated_summary": updated_summary,
        },
        "output": {
            "answer": message,
            "artifacts": [],
            "sources": [],
        },
        "metadata": {
            "data_depth": "L1",
            "reasoning_mode": "DATA_ONLY",
            "tools_invoked": [],
            "usage": {"total_duration_ms": 0, "rate_limit_remaining": None},
        },
        "warnings": warnings or [],
        "suggestions": suggestions or [],
        "error": {
            "code": code,
            "message": message,
            "options": options or [],
            "retry_after_s": retry_after_s,
        },
    }


def make_success_response(trace_id: str, session_id: str, answer: str,
                          tools_invoked: list, duration_ms: int,
                          data_depth: str = "L1",
                          reasoning_mode: str = "DATA_ONLY",
                          artifacts: list = None, sources: list = None,
                          warnings: list = None, suggestions: list = None,
                          updated_summary: str = None):
    """Build a contract-compliant success envelope."""
    return {
        "schema_version": SCHEMA_VERSION,
        "trace_id": trace_id,
        "status": "ok",
        "session": {
            "session_id": session_id,
            "updated_summary": updated_summary,
        },
        "output": {
            "answer": answer,
            "artifacts": artifacts or [],
            "sources": sources or [],
        },
        "metadata": {
            "data_depth": data_depth,
            "reasoning_mode": reasoning_mode,
            "tools_invoked": tools_invoked,
            "usage": {
                "total_duration_ms": duration_ms,
                "rate_limit_remaining": 500,
            },
        },
        "warnings": warnings or [],
        "suggestions": suggestions or [],
        "error": None,
    }


# ─── Main Endpoint ───────────────────────────────────────────────────────────

@app.post("/agent/query")
async def agent_query(request: Request):
    start = time.time()
    body = await request.json()

    # ── Manual validation (contract §1.3) ──

    trace_id = body.get("trace_id", "unknown")
    session_id = body.get("session", {}).get("session_id")

    if not body.get("trace_id"):
        return JSONResponse(content=make_error_response(
            trace_id="unknown",
            session_id=session_id or "unknown",
            code="INVALID_REQUEST",
            message="Missing required field: trace_id",
        ))

    if not session_id:
        return JSONResponse(content=make_error_response(
            trace_id=trace_id,
            session_id="unknown",
            code="INVALID_REQUEST",
            message="Missing required field: session.session_id",
        ))

    query = body.get("query", "").strip()
    if not query:
        return JSONResponse(content=make_error_response(
            trace_id=trace_id,
            session_id=session_id,
            code="INVALID_REQUEST",
            message="Missing or empty field: query",
        ))

    schema_v = body.get("schema_version", "")
    # Contract §10: lower versions → best-effort + warning; higher/unknown → error
    if schema_v and schema_v != SCHEMA_VERSION:
        try:
            incoming = float(schema_v)
            current = float(SCHEMA_VERSION)
            if incoming > current:
                return JSONResponse(content=make_error_response(
                    trace_id=trace_id,
                    session_id=session_id,
                    code="SCHEMA_MISMATCH",
                    message=f"Unsupported schema version: '{schema_v}'. Max supported: '{SCHEMA_VERSION}'",
                ))
            # Lower version → best-effort, continue with warning
        except ValueError:
            return JSONResponse(content=make_error_response(
                trace_id=trace_id,
                session_id=session_id,
                code="SCHEMA_MISMATCH",
                message=f"Invalid schema version: '{schema_v}'. Expected format: 'X.Y'",
            ))
    elif not schema_v:
        return JSONResponse(content=make_error_response(
            trace_id=trace_id,
            session_id=session_id,
            code="INVALID_REQUEST",
            message="Missing required field: schema_version",
        ))

    # ── Handle history truncation ──

    warnings = []

    # Add schema uplevel warning if lower version
    if schema_v != SCHEMA_VERSION:
        warnings.append({
            "code": "SCHEMA_VERSION_UPLEVEL",
            "message": f"Request used schema '{schema_v}'; server is at '{SCHEMA_VERSION}'. Best-effort parse applied.",
            "details": {"requested": schema_v, "current": SCHEMA_VERSION},
        })

    history = body.get("session", {}).get("history", [])
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
        warnings.append({
            "code": "HISTORY_TRUNCATED",
            "message": f"History exceeded {MAX_HISTORY} entries; truncated to last {MAX_HISTORY}.",
            "details": {"original_count": len(body["session"]["history"])},
        })

    # ── Validate constraints enums ──

    VALID_DATA_MODES = {"live", "replay"}
    VALID_MAX_DEPTHS = {"L1", "L2", "auto"}

    data_mode = body.get("constraints", {}).get("data_mode", "live")
    max_depth = body.get("constraints", {}).get("max_depth", "auto")

    if data_mode not in VALID_DATA_MODES:
        return JSONResponse(content=make_error_response(
            trace_id=trace_id,
            session_id=session_id,
            code="INVALID_REQUEST",
            message=f"Invalid constraints.data_mode: '{data_mode}'. Must be one of: {sorted(VALID_DATA_MODES)}",
            warnings=warnings,
        ))

    if max_depth not in VALID_MAX_DEPTHS:
        return JSONResponse(content=make_error_response(
            trace_id=trace_id,
            session_id=session_id,
            code="INVALID_REQUEST",
            message=f"Invalid constraints.max_depth: '{max_depth}'. Must be one of: {sorted(VALID_MAX_DEPTHS)}",
            warnings=warnings,
        ))

    # ── Check for replay mode ──

    if data_mode == "replay":
        warnings.append({
            "code": "DATA_MODE_REPLAY",
            "message": "DATA_MODE=replay active. Using static fixtures.",
            "details": {},
        })

    # ─── Real Agent Integration ──
    from football_agent import run_agent, ContractError

    try:
        # Map history list of dicts from pydantic to list of dicts for agent
        agent_history = body.get("session", {}).get("history", [])

        allow_live = body.get("constraints", {}).get("allow_live_fetch", True)
        
        result = await run_agent(
            query=query,
            session_id=session_id,
            trace_id=trace_id,
            history=agent_history,
            memory_summary=body.get("session", {}).get("memory_summary"),
            data_mode=data_mode,
            max_depth=max_depth,
            allow_live_fetch=allow_live,
        )

        elapsed_ms = int((time.time() - start) * 1000)
        
        # Combine protocol warnings (like schema mismatch) with agent warnings
        agent_warnings = result.warnings if isinstance(result.warnings, list) else []
        combined_warnings = warnings + agent_warnings

        suggestions = result.suggestions if isinstance(result.suggestions, list) else []
        suggestions = suggestions[:3]

        return JSONResponse(content=make_success_response(
            trace_id=trace_id,
            session_id=session_id,
            answer=result.answer,
            tools_invoked=result.tools_invoked or [],
            duration_ms=elapsed_ms,
            data_depth=result.data_depth,
            reasoning_mode=result.reasoning_mode,
            artifacts=result.artifacts,
            sources=result.sources,
            warnings=combined_warnings,
            suggestions=suggestions,
            updated_summary=result.updated_summary,
        ))

    except ContractError as e:
        return JSONResponse(content=make_error_response(
            trace_id=trace_id,
            session_id=session_id,
            code=e.code,
            message=e.message,
            options=e.options,
            warnings=warnings,
        ))

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(content=make_error_response(
            trace_id=trace_id,
            session_id=session_id,
            code="UPSTREAM_DOWN",
            message=f"Internal agent error: {str(e)}",
            warnings=warnings,
        ))


# ─── Health Check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "service": "footiq-agent",
        "status": "ok",
        "schema_version": SCHEMA_VERSION,
        "data_mode": DATA_MODE,
    }
