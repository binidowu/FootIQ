import { useState, useRef, useEffect, type KeyboardEvent } from "react";

interface Props {
    onSend: (text: string) => void;
    isLoading: boolean;
}

export default function ChatInput({ onSend, isLoading }: Props) {
    const [value, setValue] = useState("");
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    // Auto-resize textarea
    useEffect(() => {
        const el = textareaRef.current;
        if (el) {
            el.style.height = "auto";
            el.style.height = Math.min(el.scrollHeight, 140) + "px";
        }
    }, [value]);

    const handleSubmit = () => {
        if (!value.trim() || isLoading) return;
        onSend(value);
        setValue("");
    };

    const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
        }
    };

    return (
        <div className="chat-input-wrapper">
            <div className="chat-input-container">
                <textarea
                    ref={textareaRef}
                    id="chat-input"
                    className="chat-input"
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask about any football player…"
                    rows={1}
                    disabled={isLoading}
                />
                <button
                    id="send-button"
                    className="send-button"
                    onClick={handleSubmit}
                    disabled={!value.trim() || isLoading}
                    aria-label="Send message"
                >
                    {isLoading ? (
                        <span className="spinner" />
                    ) : (
                        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                            <path
                                d="M3 10L17 3L10 17L9 11L3 10Z"
                                fill="currentColor"
                            />
                        </svg>
                    )}
                </button>
            </div>
            <p className="input-hint">
                Press <kbd>Enter</kbd> to send · <kbd>Shift+Enter</kbd> for new line
            </p>
        </div>
    );
}
