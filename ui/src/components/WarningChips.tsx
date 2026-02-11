import type { ContractWarning } from "../types/contract";

interface Props {
    warnings: ContractWarning[];
}

export default function WarningChips({ warnings }: Props) {
    if (!warnings.length) return null;

    return (
        <div className="warning-chips" id="warning-chips">
            {warnings.map((w, i) => (
                <span key={i} className="warning-chip" title={w.message}>
                    <span className="warning-icon">⚠️</span>
                    <span className="warning-code">{w.code}</span>
                    <span className="warning-msg">{w.message}</span>
                </span>
            ))}
        </div>
    );
}
