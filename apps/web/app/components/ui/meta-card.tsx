import type { LucideIcon } from "lucide-react";

import { Badge } from "./badge";

export function MetaCard({ icon: Icon, label, value, mono, tone }: { icon: LucideIcon; label: string; value: string; mono?: boolean; tone?: string }) {
  return (
    <article className="metaCard">
      <Icon size={22} />
      <span>{label}</span>
      {tone ? <Badge tone={tone}>{value}</Badge> : <strong className={mono ? "mono" : ""}>{value}</strong>}
    </article>
  );
}
