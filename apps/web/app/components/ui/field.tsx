import { Badge } from "./badge";

export function Field({ label, value, tone, mono }: { label: string; value: string; tone?: string; mono?: boolean }) {
  return (
    <div className="field">
      <small>{label}</small>
      {tone ? <Badge tone={tone}>{value}</Badge> : <strong className={mono ? "mono" : ""}>{value}</strong>}
    </div>
  );
}
