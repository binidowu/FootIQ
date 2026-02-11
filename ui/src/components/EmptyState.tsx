const EXAMPLE_QUERIES = [
    "How is Haaland doing this season?",
    "Compare Saka and Foden",
    "Why is Salah's output dropping?",
    "Show me Palmer's xG trend",
];

interface Props {
    onSelect: (query: string) => void;
}

export default function EmptyState({ onSelect }: Props) {
    return (
        <div className="empty-state" id="empty-state">
            <div className="empty-logo">
                <span className="logo-icon">⚽</span>
                <h1 className="logo-title">FootIQ</h1>
                <p className="logo-subtitle">AI-Powered Football Intelligence</p>
            </div>

            <div className="example-queries">
                <p className="examples-label">Try asking:</p>
                <div className="examples-grid">
                    {EXAMPLE_QUERIES.map((q, i) => (
                        <button
                            key={i}
                            className="example-card"
                            onClick={() => onSelect(q)}
                        >
                            <span className="example-icon">💬</span>
                            <span className="example-text">{q}</span>
                        </button>
                    ))}
                </div>
            </div>
        </div>
    );
}
