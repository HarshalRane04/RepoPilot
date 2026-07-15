import type { LucideIcon } from "lucide-react";

export function StatCard({ label, value, icon: Icon }: { label: string; value: string | number; icon?: LucideIcon }) {
  return (
    <article className="statCard">
      {Icon ? <Icon size={28} /> : null}
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}
