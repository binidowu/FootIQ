import { useChat } from "./hooks/useChat";
import ChatMessageList from "./components/ChatMessageList";
import ChatInput from "./components/ChatInput";
import EmptyState from "./components/EmptyState";
import "./index.css";

export default function App() {
  const { messages, isLoading, sessionId, dataMode, setDataMode, send, resetSession } = useChat();
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
          {/* Data Mode Toggle */}
          <div className="mode-toggle" id="mode-toggle">
            <button
              className={`mode-btn ${dataMode === "live" ? "active" : ""}`}
              onClick={() => setDataMode("live")}
              title="Live mode — real API calls"
            >
              <span className="mode-dot live" />
              Live
            </button>
            <button
              className={`mode-btn ${dataMode === "replay" ? "active" : ""}`}
              onClick={() => setDataMode("replay")}
              title="Replay mode — cached fixtures only"
            >
              <span className="mode-dot replay" />
              Replay
            </button>
          </div>

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
          <EmptyState onSelect={send} dataMode={dataMode} />
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
