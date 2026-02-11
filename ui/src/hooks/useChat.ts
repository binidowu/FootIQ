import { useState, useCallback } from "react";
import type { ChatMessage, QueryResponse } from "../types/contract";
import { queryAgent } from "../api/client";

function uid(): string {
    return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function newSessionId(): string {
    return `sess_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`;
}

export function useChat() {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [sessionId, setSessionId] = useState(() => newSessionId());
    const [lastTraceId, setLastTraceId] = useState<string | null>(null);


    const send = useCallback(
        async (text: string) => {
            const trimmed = text.trim();
            if (!trimmed || isLoading) return;

            // Add user message
            const userMsg: ChatMessage = {
                id: uid(),
                role: "user",
                content: trimmed,
                timestamp: Date.now(),
            };
            setMessages((prev) => [...prev, userMsg]);
            setIsLoading(true);

            try {
                const response: QueryResponse = await queryAgent({
                    session_id: sessionId,
                    query: trimmed,
                });

                setLastTraceId(response.trace_id);

                // Update session_id if server assigned one
                if (response.session?.session_id) {
                    setSessionId(response.session.session_id);
                }

                const assistantMsg: ChatMessage = {
                    id: uid(),
                    role: response.status === "error" ? "error" : "assistant",
                    content: response.output?.answer || "(No response)",
                    timestamp: Date.now(),
                    response,
                };
                setMessages((prev) => [...prev, assistantMsg]);
            } catch (err) {
                const errorMsg: ChatMessage = {
                    id: uid(),
                    role: "error",
                    content:
                        err instanceof Error
                            ? err.message
                            : "Something went wrong. Please try again.",
                    timestamp: Date.now(),
                };
                setMessages((prev) => [...prev, errorMsg]);
            } finally {
                setIsLoading(false);
            }
        },
        [isLoading, sessionId]
    );

    const resetSession = useCallback(() => {
        setMessages([]);
        setSessionId(newSessionId());
        setLastTraceId(null);
    }, []);

    return {
        messages,
        isLoading,
        sessionId,
        lastTraceId,
        send,
        resetSession,
    };
}
