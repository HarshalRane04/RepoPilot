export function Segment({ active, disabled, label, onClick }: { active?: boolean; disabled?: boolean; label: string; onClick?: () => void }) {
  return <button aria-pressed={Boolean(active)} className={active ? "segment active" : "segment"} disabled={disabled} onClick={onClick} type="button">{label}</button>;
}
