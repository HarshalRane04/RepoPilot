import { EmptyState } from "./empty-state";

export function NumberedList({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) {
    return <EmptyState text={empty} />;
  }
  return <ol className="numberedList">{items.map((item) => <li key={item}>{item}</li>)}</ol>;
}

export function Bullets({ items, empty = "No entries recorded." }: { items: string[]; empty?: string }) {
  if (items.length === 0) {
    return <EmptyState text={empty} />;
  }
  return <ul className="bullets">{items.map((item) => <li key={item}>{item}</li>)}</ul>;
}
