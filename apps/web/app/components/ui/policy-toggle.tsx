import { Badge } from "./badge";

export function PolicyToggle({ label, enabled }: { label: string; enabled: boolean }) {
  return (
    <div className="policyToggle">
      <span>{label}</span>
      <Badge tone={enabled ? "success" : "neutral"}>{enabled ? "Enabled" : "Disabled"}</Badge>
    </div>
  );
}
