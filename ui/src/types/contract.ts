/* ─── FootIQ Contract Types (v1.1) ─────────────────────────────────────────── */
/* Source of truth: docs/API_CONTRACT.md (frozen)                              */

// ─── Request ──────────────────────────────────────────────────────────────────

export interface QueryRequest {
    session_id?: string;
    query: string;
    constraints?: {
        data_mode?: "live" | "replay";
        max_depth?: "L1" | "L2" | "auto";
        allow_live_fetch?: boolean;
    };
}

// ─── Response ─────────────────────────────────────────────────────────────────

export interface Artifact {
    type: "plot" | "heatmap" | "stat_table";
    url?: string;
    data?: Record<string, unknown>[];
    label: string;
}

export interface Source {
    id: string;
    title: string;
    relevance: number;
}

export interface ToolInvocation {
    tool: string;
    duration_ms?: number;
    cache_hit?: boolean;
    ttl_remaining_s?: number;
}

export interface ContractWarning {
    code: string;
    message: string;
    details?: Record<string, unknown>;
}

export interface ContractError {
    code: string;
    message: string;
    options?: { label: string; athlete_id: string }[];
    retry_after_s?: number | null;
}

export interface QueryResponse {
    schema_version: string;
    trace_id: string;
    status: "ok" | "error";
    session: {
        session_id: string;
        updated_summary?: string;
    };
    output: {
        answer: string;
        artifacts: Artifact[];
        sources: Source[];
    };
    metadata: {
        data_depth: "L1" | "L2";
        reasoning_mode: "DATA_ONLY" | "SYNTHESIS";
        tools_invoked: ToolInvocation[];
        usage?: {
            total_duration_ms?: number;
            rate_limit_remaining?: number | null;
        };
    };
    warnings: ContractWarning[];
    suggestions: string[];
    error: ContractError | null;
}

// ─── UI-level message model ───────────────────────────────────────────────────

export type MessageRole = "user" | "assistant" | "error";

export interface ChatMessage {
    id: string;
    role: MessageRole;
    content: string;
    timestamp: number;
    /** Only set on assistant messages */
    response?: QueryResponse;
}
