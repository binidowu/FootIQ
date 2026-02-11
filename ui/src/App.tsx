import { useChat } from "./hooks/useChat";
import ChatMessageList from "./components/ChatMessageList";
import ChatInput from "./components/ChatInput";
import EmptyState from "./components/EmptyState";
import "./index.css";

export default function App() {
  const { messages, isLoading, sessionId, send, resetSession } = useChat();
  const showEmpty = messages.length === 0 && !isLoading;

  return (
    <div className="app-shell">
      {/* Header */}
      <header className="app-header" id="app-header">
        <div className="header-left">
          <span className="header-logo">⚽</span>
          <h1 className="header-title">FootIQ</h1>
        </div>
        <div className="header-right">
          <span className="session-badge" title={`Session: ${sessionId}`}>
            {sessionId.slice(0, 12)}…
          </span>
          <button
            className="reset-button"
            onClick={resetSession}
            title="Start new session"
            id="reset-session"
          >
            ↻ New Chat
          </button>
        </div>
      </header>

      {/* Main */}
      <main className="app-main">
        {showEmpty ? (
          <EmptyState onSelect={send} />
        ) : (
          <ChatMessageList
            messages={messages}
            isLoading={isLoading}
            onSuggestionClick={send}
          />
        )}
      </main>

      {/* Composer */}
      <footer className="app-footer">
        <ChatInput onSend={send} isLoading={isLoading} />
      </footer>
    </div>
  );
}
