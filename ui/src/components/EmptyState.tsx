const EXAMPLE_QUERIES: Record<"live" | "replay", string[]> = {
    live: [
        "How is Haaland doing this season?",
        "How is Bellingham doing this season?",
        "How is De Bruyne doing this season?",
        "Compare Haaland and Mbappe",
    ],
    replay: [
        "How is Haaland doing this season?",
        "Analyze Haaland xG trend",
        "How is Saka doing?",
        "Why is Haaland's output dropping?",
    ],
};

interface Props {
    onSelect: (query: string) => void;
    dataMode: "live" | "replay";
}

export default function EmptyState({ onSelect, dataMode }: Props) {
    const queries = EXAMPLE_QUERIES[dataMode];

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
                    {queries.map((q, i) => (
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
