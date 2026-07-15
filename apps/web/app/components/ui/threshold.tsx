import { Badge } from "./badge";

export function Threshold({ label, tone, value }: { label: string; tone: string; value: string }) {
  return <div className="threshold"><span>{label}</span><Badge tone={tone}>{value}</Badge></div>;
}
