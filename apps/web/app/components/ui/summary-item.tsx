import { ChevronRight } from "lucide-react";

export function SummaryItem({ icon: Icon, label, value, tone }: { icon: React.ElementType; label: string; value: string | number; tone: string }) {
  return (
    <div className="summaryItem">
      <span className={`summaryIcon ${tone}`}><Icon size={24} /></span>
      <span>
        <small>{label}</small>
        <strong>{value}</strong>
      </span>
      <ChevronRight size={18} />
    </div>
  );
}
