import { EmptyState } from "./empty-state";

export function CheckList({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) return <EmptyState text={empty} />;
  return (
    <div className="checkList">
      {items.map((item, index) => <span key={index}>{item}</span>)}
    </div>
  );
}

export function NumberedList({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) return <EmptyState text={empty} />;
  return (
    <ol className="numberedList">
      {items.map((item, index) => <li key={index}>{item}</li>)}
    </ol>
  );
}

export function Bullets({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) return <EmptyState text={empty} />;
  return (
    <ul className="bullets">
      {items.map((item, index) => <li key={index}>{item}</li>)}
    </ul>
  );
}
