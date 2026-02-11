const express = require('express');
const crypto = require('crypto');
const path = require('path');

const app = express();
app.use(express.json());

// --- Static file serving for plots ---
app.use('/static/plots', express.static(path.join(__dirname, 'public', 'plots')));

// --- Configuration ---
function msFromEnv(name, fallbackMs) {
    const raw = process.env[name];
    if (!raw) return fallbackMs;
    const parsed = Number(raw);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallbackMs;
}

const PYTHON_AGENT_URL = process.env.PYTHON_AGENT_URL || 'http://127.0.0.1:8000';
const PORT = process.env.PORT || 3000;
const SESSION_TTL_MS = msFromEnv('SESSION_TTL_MS', 30 * 60 * 1000);        // 30 minutes
const SESSION_CLEANUP_MS = msFromEnv('SESSION_CLEANUP_MS', 5 * 60 * 1000); // every 5 minutes
const PLOT_CLEANUP_MS = msFromEnv('PLOT_CLEANUP_MS', 60 * 60 * 1000);       // every 60 minutes
const PLOT_MAX_AGE_MS = msFromEnv('PLOT_MAX_AGE_MS', 2 * 60 * 60 * 1000);   // 2 hours
const MAX_HISTORY = 10;

// --- Session Store ---
const sessions = new Map();

function getOrCreateSession(sessionId) {
    if (!sessionId) {
        sessionId = `sess_${crypto.randomUUID().slice(0, 8)}`;
    }
    if (!sessions.has(sessionId)) {
        sessions.set(sessionId, {
            session_id: sessionId,
            history: [],
            memory_summary: null,
            last_active: Date.now(),
        });
    }
    const session = sessions.get(sessionId);
    session.last_active = Date.now();
    return session;
}

function truncateHistory(history) {
    if (history.length > MAX_HISTORY) {
        return history.slice(-MAX_HISTORY);
    }
    return history;
}

// Session cleanup cron
setInterval(() => {
    const now = Date.now();
    let purged = 0;
    for (const [id, session] of sessions) {
        if (now - session.last_active > SESSION_TTL_MS) {
            sessions.delete(id);
            purged++;
        }
    }
    if (purged > 0) {
        console.log(`[session-cleanup] Purged ${purged} expired session(s). Active: ${sessions.size}`);
    }
}, SESSION_CLEANUP_MS);

// Plot cleanup cron
const fs = require('fs');
setInterval(() => {
    const plotDir = path.join(__dirname, 'public', 'plots');
    if (!fs.existsSync(plotDir)) return;

    const now = Date.now();
    let deleted = 0;
    for (const file of fs.readdirSync(plotDir)) {
        const filepath = path.join(plotDir, file);
        const stat = fs.statSync(filepath);
        if (now - stat.mtimeMs > PLOT_MAX_AGE_MS) {
            fs.unlinkSync(filepath);
            deleted++;
        }
    }
    if (deleted > 0) {
        console.log(`[plot-cleanup] Deleted ${deleted} expired plot(s).`);
    }
}, PLOT_CLEANUP_MS);

// --- Trace ID Generation ---
function generateTraceId() {
    const now = new Date();
    const ts = now.toISOString().replace(/\D/g, '').slice(0, 14); // YYYYMMDDHHMMSS
    const rand = crypto.randomUUID().slice(0, 4);
    return `ftiq_${rand}_${ts}`;
}

// --- Main Query Endpoint ---
app.post('/query', async (req, res) => {
    const { session_id, query, constraints } = req.body;

    // Basic validation on Node side
    if (!query || query.trim() === '') {
        return res.status(400).json({ error: 'query is required and must be non-empty.' });
    }

    const traceId = generateTraceId();
    const session = getOrCreateSession(session_id);
    const trimmedQuery = query.trim();

    // Contract semantics: send only prior conversation in history.
    const priorHistory = truncateHistory(session.history);


    // Build the contract-compliant request envelope
    const requestEnvelope = {
        schema_version: '1.1',
        trace_id: traceId,
        session: {
            session_id: session.session_id,
            history: priorHistory,
            memory_summary: session.memory_summary,
        },
        query: trimmedQuery,
        constraints: {
            data_mode: constraints?.data_mode || 'live',
            max_depth: constraints?.max_depth || 'auto',
            allow_live_fetch: constraints?.allow_live_fetch !== undefined
                ? constraints.allow_live_fetch
                : true,
        },
    };

    try {
        // Forward to Python agent
        const agentResponse = await fetch(`${PYTHON_AGENT_URL}/agent/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestEnvelope),
        });

        const data = await agentResponse.json();

        // Update session from Python's response
        session.history.push({ role: 'user', content: trimmedQuery });
        if (data.session?.updated_summary) {
            session.memory_summary = data.session.updated_summary;
        }
        if (data.output?.answer) {
            session.history.push({ role: 'assistant', content: data.output.answer });
        }
        session.history = truncateHistory(session.history);

        return res.json(data);
    } catch (err) {
        console.error(`[${traceId}] Python agent error:`, err.message);

        const fallbackAnswer = 'The analysis service is currently unavailable. Please try again shortly.';
        session.history.push({ role: 'user', content: trimmedQuery });
        session.history.push({ role: 'assistant', content: fallbackAnswer });
        session.history = truncateHistory(session.history);

        // Return a contract-compliant error envelope
        return res.json({
            schema_version: '1.1',
            trace_id: traceId,
            status: 'error',
            session: { session_id: session.session_id, updated_summary: session.memory_summary },
            output: {
                answer: fallbackAnswer,
                artifacts: [],
                sources: [],
            },
            metadata: {
                data_depth: 'L1',
                reasoning_mode: 'DATA_ONLY',
                tools_invoked: [],
                usage: { total_duration_ms: 0, rate_limit_remaining: null },
            },
            warnings: [],
            suggestions: ['Try again in a moment'],
            error: {
                code: 'UPSTREAM_DOWN',
                message: `Python agent unreachable: ${err.message}`,
                options: [],
                retry_after_s: 10,
            },
        });
    }
});

// --- Health Check ---
app.get('/health', (req, res) => {
    res.json({
        service: 'footiq-gateway',
        status: 'ok',
        active_sessions: sessions.size,
        uptime_s: Math.floor(process.uptime()),
    });
});

// --- Start ---
app.listen(PORT, () => {
    console.log(`[FootIQ Gateway] Running on http://localhost:${PORT}`);
    console.log(`[FootIQ Gateway] Python agent URL: ${PYTHON_AGENT_URL}`);
});
