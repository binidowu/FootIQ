import type { ChatMessage } from "../types/contract";
import MarkdownAnswer from "./MarkdownAnswer";
import WarningChips from "./WarningChips";
import SuggestionButtons from "./SuggestionButtons";
import ArtifactPanel from "./ArtifactPanel";
import DebugPanel from "./DebugPanel";

interface Props {
    message: ChatMessage;
    onSuggestionClick: (text: string) => void;
}

export default function MessageBubble({ message, onSuggestionClick }: Props) {
    const { role, content, response } = message;

    if (role === "user") {
        return (
            <div className="message-bubble user">
                <div className="bubble-content">
                    <p>{content}</p>
                </div>
                <div className="bubble-avatar">
                    <span className="avatar-icon">👤</span>
                </div>
            </div>
        );
    }

    // Assistant or Error
    const isError = role === "error" || response?.status === "error";

    return (
        <div className={`message-bubble assistant ${isError ? "error" : ""}`}>
            <div className="bubble-avatar">
                <span className="avatar-icon">⚽</span>
            </div>
            <div className="bubble-content">
                {/* Error banner */}
                {isError && response?.error && (
                    <div className="error-banner" id="error-banner">
                        <span className="error-code">{response.error.code}</span>
                        <span className="error-message">{response.error.message}</span>
                        {response.error.options && response.error.options.length > 0 && (
                            <div className="error-options">
                                <p>Did you mean:</p>
                                <ul>
                                    {response.error.options.map((opt, i) => (
                                        <li key={i}>
                                            <button
                                                className="option-button"
                                                onClick={() => onSuggestionClick(opt.label)}
                                            >
                                                {opt.label}
                                            </button>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </div>
                )}

                {/* Answer content */}
                <MarkdownAnswer content={content} />

                {/* Artifacts */}
                {response?.output?.artifacts && response.output.artifacts.length > 0 && (
                    <ArtifactPanel artifacts={response.output.artifacts} />
                )}

                {/* Warnings */}
                {response?.warnings && response.warnings.length > 0 && (
                    <WarningChips warnings={response.warnings} />
                )}

                {/* Suggestions */}
                {response?.suggestions && response.suggestions.length > 0 && (
                    <SuggestionButtons
                        suggestions={response.suggestions.slice(0, 3)}
                        onClick={onSuggestionClick}
                    />
                )}

                {/* Debug */}
                {response && <DebugPanel response={response} />}
            </div>
        </div>
    );
}
