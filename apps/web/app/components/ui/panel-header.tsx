import type { LucideIcon } from "lucide-react";

export function PanelHeader({ title, icon: Icon }: { title: string; icon?: LucideIcon }) {
  return (
    <header className="panelHeader">
      <h2>{Icon ? <Icon size={22} /> : null}{title}</h2>
    </header>
  );
}
