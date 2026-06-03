import { EmptyState } from "./empty-state";
import { Badge } from "./badge";

export function PillList({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) return <EmptyState text={empty} />;
  return (
    <div className="pillList">
      {items.map((item, index) => <Badge key={index} tone="info">{item}</Badge>)}
    </div>
  );
}
