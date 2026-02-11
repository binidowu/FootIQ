import type { ContractWarning } from "../types/contract";

/** Warning codes that are infrastructure noise — hidden from demo UI */
const SUPPRESSED_CODES = new Set(["USED_CACHED_DATA"]);

interface Props {
    warnings: ContractWarning[];
}

export default function WarningChips({ warnings }: Props) {
    const visible = warnings.filter((w) => !SUPPRESSED_CODES.has(w.code));
    if (!visible.length) return null;

    return (
        <div className="warning-chips" id="warning-chips">
            {visible.map((w, i) => (
                <span key={i} className="warning-chip" title={w.message}>
                    <span className="warning-icon">⚠️</span>
                    <span className="warning-code">{w.code}</span>
                    <span className="warning-msg">{w.message}</span>
                </span>
            ))}
        </div>
    );
}
