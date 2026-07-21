import { consoleHash, type View } from "../../lib/operator-console-state.ts";

export function Breadcrumb({ trail }: { trail: Array<{ label: string; view?: View; entityId?: string }> }) {
  return (
    <nav aria-label="Breadcrumb" className="breadcrumb">
      <ol>
        {trail.map((item, index) => {
          const current = index === trail.length - 1;
          return (
            <li key={`${item.label}-${index}`}>
              {!current && item.view
                ? <a href={`#${consoleHash(item.view, { entityId: item.entityId })}`}>{item.label}</a>
                : <span aria-current={current ? "page" : undefined}>{item.label}</span>}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
