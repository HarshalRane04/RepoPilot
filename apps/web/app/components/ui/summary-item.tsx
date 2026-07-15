import { ChevronRight, type LucideIcon } from "lucide-react";

export function SummaryItem({ icon: Icon, label, onClick, value, tone }: { icon: LucideIcon; label: string; onClick?: () => void; value: string | number; tone: string }) {
  const content = (
    <>
      <span className={`summaryIcon ${tone}`}><Icon size={24} /></span>
      <span><small>{label}</small><strong>{value}</strong></span>
      {onClick ? <ChevronRight size={18} aria-hidden="true" /> : null}
    </>
  );
  return onClick
    ? <button aria-label={`${label}: ${value}`} className="summaryItem" onClick={onClick} type="button">{content}</button>
    : <div className="summaryItem">{content}</div>;
}
