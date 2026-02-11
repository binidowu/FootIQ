import { useRef, useEffect } from "react";
import type { ChatMessage } from "../types/contract";
import MessageBubble from "./MessageBubble";

interface Props {
    messages: ChatMessage[];
    isLoading: boolean;
    onSuggestionClick: (text: string) => void;
}

export default function ChatMessageList({
    messages,
    isLoading,
    onSuggestionClick,
}: Props) {
    const bottomRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages, isLoading]);

    if (messages.length === 0 && !isLoading) {
        return null; // Empty state handled by parent
    }

    return (
        <div className="message-list" id="message-list">
            {messages.map((msg) => (
                <MessageBubble
                    key={msg.id}
                    message={msg}
                    onSuggestionClick={onSuggestionClick}
                />
            ))}
            {isLoading && (
                <div className="message-bubble assistant loading-bubble">
                    <div className="bubble-avatar">
                        <span className="avatar-icon">⚽</span>
                    </div>
                    <div className="bubble-content">
                        <div className="typing-indicator">
                            <span></span><span></span><span></span>
                        </div>
                        <p className="loading-text">Analyzing...</p>
                    </div>
                </div>
            )}
            <div ref={bottomRef} />
        </div>
    );
}
