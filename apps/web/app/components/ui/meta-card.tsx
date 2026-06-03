export function MetaCard({ icon: Icon, label, value, mono }: { icon: React.ElementType; label: string; value: string; mono?: boolean }) {
  return (
    <article className="metaCard">
      <Icon size={22} />
      <span>{label}</span>
      <strong className={mono ? "mono" : ""}>{value}</strong>
    </article>
  );
}
