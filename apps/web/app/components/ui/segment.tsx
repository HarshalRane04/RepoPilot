export function Segment({ active, disabled, label, icon: Icon, onClick }: { active?: boolean; disabled?: boolean; label: string; icon?: React.ElementType; onClick?: () => void }) {
  return (
    <button className={active ? "segment active" : "segment"} disabled={disabled} onClick={onClick} type="button">
      {Icon ? <Icon size={16} /> : null}
      {label}
    </button>
  );
}
