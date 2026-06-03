export function KeyValue({ icon: Icon, label, value }: { icon?: React.ElementType; label: string; value: string }) {
  return (
    <div className="keyValue">
      {Icon ? <Icon size={18} /> : null}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
