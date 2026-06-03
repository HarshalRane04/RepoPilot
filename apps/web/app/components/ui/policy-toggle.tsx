export function PolicyToggle({ label, enabled }: { label: string; enabled: boolean }) {
  return (
    <div className="policyToggle">
      <span>{label}</span>
      <span style={{ color: enabled ? "var(--green)" : "var(--text-2)", fontWeight: 740, fontSize: 13 }}>{enabled ? "Enabled" : "Disabled"}</span>
    </div>
  );
}
