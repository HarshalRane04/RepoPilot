import type { ReactNode } from "react";

export function Panel({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={className ? `panel ${className}` : "panel"}>{children}</section>;
}

export function PanelHeader({ title, icon: Icon }: { title: string; icon?: React.ElementType }) {
  return (
    <header className="panelHeader">
      <h2>{Icon ? <Icon size={22} /> : null}{title}</h2>
    </header>
  );
}

export function SummaryPanel({ children }: { children: ReactNode }) {
  return <aside className="panel summaryPanel">{children}</aside>;
}

export function ContextPanel({ children }: { children: ReactNode }) {
  return <aside className="panel contextPanel">{children}</aside>;
}
