interface Props {
    suggestions: string[];
    onClick: (text: string) => void;
}

export default function SuggestionButtons({ suggestions, onClick }: Props) {
    if (!suggestions.length) return null;

    return (
        <div className="suggestion-buttons" id="suggestion-buttons">
            {suggestions.slice(0, 3).map((s, i) => (
                <button
                    key={i}
                    className="suggestion-btn"
                    onClick={() => onClick(s)}
                >
                    <span className="suggestion-arrow">→</span> {s}
                </button>
            ))}
        </div>
    );
}
