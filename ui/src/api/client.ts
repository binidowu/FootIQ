import type { QueryRequest, QueryResponse } from "../types/contract";

const API_BASE = "/query"; // proxied by Vite to Node gateway

/**
 * Send a query to the FootIQ Node gateway.
 * Always returns a contract-compliant QueryResponse or throws.
 */
export async function queryAgent(req: QueryRequest): Promise<QueryResponse> {
    const res = await fetch(API_BASE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
    });

    if (!res.ok && res.status !== 200) {
        // Node gateway should always return 200, but handle edge cases
        throw new Error(`Gateway returned HTTP ${res.status}`);
    }

    const data: QueryResponse = await res.json();

    // Runtime guards: verify required envelope fields exist
    if (!data.schema_version || !data.trace_id || !data.status) {
        throw new Error("Malformed response: missing required envelope fields");
    }
    if (!data.session?.session_id) {
        throw new Error("Malformed response: missing session_id");
    }
    if (!Array.isArray(data.warnings)) {
        data.warnings = [];
    }
    if (!Array.isArray(data.suggestions)) {
        data.suggestions = [];
    }

    return data;
}
