import { useState } from "react";
import type { QueryResponse } from "../types/contract";

interface Props {
    response: QueryResponse;
}

export default function DebugPanel({ response }: Props) {
    const [open, setOpen] = useState(false);

    const { trace_id, metadata } = response;

    return (
        <div className="debug-panel" id="debug-panel">
            <button
                className="debug-toggle"
                onClick={() => setOpen(!open)}
                aria-expanded={open}
            >
                <span className="debug-icon">🔍</span>
                <span>Debug</span>
                <span className={`debug-chevron ${open ? "open" : ""}`}>▶</span>
            </button>

            {open && (
                <div className="debug-details">
                    <div className="debug-row">
                        <span className="debug-label">Trace ID</span>
                        <code className="debug-value">{trace_id}</code>
                    </div>
                    <div className="debug-row">
                        <span className="debug-label">Data Depth</span>
                        <span className={`depth-badge ${metadata.data_depth}`}>
                            {metadata.data_depth}
                        </span>
                    </div>
                    <div className="debug-row">
                        <span className="debug-label">Reasoning</span>
                        <span className="debug-value">{metadata.reasoning_mode}</span>
                    </div>
                    {metadata.usage?.total_duration_ms != null && (
                        <div className="debug-row">
                            <span className="debug-label">Duration</span>
                            <span className="debug-value">
                                {metadata.usage.total_duration_ms}ms
                            </span>
                        </div>
                    )}
                    {metadata.tools_invoked.length > 0 && (
                        <div className="debug-row tools-row">
                            <span className="debug-label">Tools</span>
                            <div className="tool-list">
                                {metadata.tools_invoked.map((t, i) => (
                                    <span key={i} className="tool-chip">
                                        {t.tool}
                                        {t.cache_hit && <span className="cache-badge">cached</span>}
                                        {t.duration_ms != null && (
                                            <span className="tool-duration">{t.duration_ms}ms</span>
                                        )}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
