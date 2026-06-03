import { ChevronRight } from "lucide-react";

type RiskCounts = ReturnType<typeof import("../../operator-console").riskCounts>;

export function RiskRows({ risk, onSecurity }: { risk: RiskCounts; onSecurity: () => void }) {
  const total = Math.max(1, risk.low + risk.medium + risk.high + risk.blocked);
  const rows = [
    ["Low risk", risk.low, "success"],
    ["Medium risk", risk.medium, "warning"],
    ["High risk", risk.high, "danger"],
    ["Blocked", risk.blocked, "danger"]
  ] as const;
  return (
    <div className="riskRows">
      {rows.map(([label, value, tone]) => (
        <div className="riskRow" key={label}>
          <span><i className={tone} /> {label}</span>
          <div className="miniBar"><span className={tone} style={{ width: `${(value / total) * 100}%` }} /></div>
          <strong>{value}</strong>
        </div>
      ))}
      <button className="panelLink" onClick={onSecurity} type="button">View full risk report <ChevronRight size={16} /></button>
    </div>
  );
}
