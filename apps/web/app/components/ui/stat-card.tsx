export function StatCard({ label, value, icon: Icon }: { label: string; value: string | number; icon?: React.ElementType }) {
  return (
    <article className="statCard">
      {Icon ? <Icon size={28} /> : null}
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}
