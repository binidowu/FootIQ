import type { Artifact } from "../types/contract";

interface Props {
    artifacts: Artifact[];
}

export default function ArtifactPanel({ artifacts }: Props) {
    if (!artifacts.length) return null;

    return (
        <div className="artifact-panel" id="artifact-panel">
            {artifacts.map((art, i) => {
                if (art.type === "plot" || art.type === "heatmap") {
                    return (
                        <div className="artifact-card" key={i}>
                            {art.label && <h4 className="artifact-label">{art.label}</h4>}
                            <img
                                src={art.url}
                                alt={art.label || "Chart"}
                                className="artifact-image"
                                loading="lazy"
                            />
                        </div>
                    );
                }

                if (art.type === "stat_table" && Array.isArray(art.data) && art.data.length > 0) {
                    const columns = Object.keys(art.data[0]);
                    return (
                        <div className="artifact-card" key={i}>
                            {art.label && <h4 className="artifact-label">{art.label}</h4>}
                            <div className="table-wrapper">
                                <table className="stat-table">
                                    <thead>
                                        <tr>
                                            {columns.map((col) => (
                                                <th key={col}>{col}</th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {art.data!.map((row, ri) => (
                                            <tr key={ri}>
                                                {columns.map((col) => (
                                                    <td key={col}>{String(row[col] ?? "—")}</td>
                                                ))}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    );
                }

                return null;
            })}
        </div>
    );
}
