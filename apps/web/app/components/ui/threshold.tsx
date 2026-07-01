export function Threshold({ label, tone, value }: { label: string; tone: string; value: string }) {
  const toneColors: Record<string, string> = { success: "var(--green)", warning: "var(--amber)", danger: "var(--red)" };
  return (
    <div className="threshold">
      <span>{label}</span>
      <span style={{ color: toneColors[tone] ?? "var(--text-2)", fontWeight: 700, fontSize: 13 }}>{value}</span>
    </div>
  );
}
