import type { LucideIcon } from "lucide-react";

export function KeyValue({ label, value, icon: Icon }: { label: string; value: string; icon?: LucideIcon }) {
  return <div className="keyValue">{Icon ? <Icon size={20} /> : null}<span>{label}</span><strong>{value}</strong></div>;
}
