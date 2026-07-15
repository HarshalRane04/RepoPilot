import { EmptyState } from "./empty-state";

export function PillList({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) {
    return <EmptyState text={empty} />;
  }
  return <div className="pillList">{items.map((item) => <code key={item}>{item}</code>)}</div>;
}
