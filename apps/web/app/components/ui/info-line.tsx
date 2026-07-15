import type { LucideIcon } from "lucide-react";

export function InfoLine({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <div className="infoLine">
      <Icon size={24} />
      <span><strong>{label}</strong><small>{value}</small></span>
    </div>
  );
}
