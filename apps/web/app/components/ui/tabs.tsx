import type { ReactNode } from "react";

export function Tabs({ children }: { children: ReactNode }) {
  return <div className="tabs">{children}</div>;
}

export function Tab({ active, children, onClick }: { active?: boolean; children: ReactNode; onClick?: () => void }) {
  return (
    <button className={active ? "tab active" : "tab"} onClick={onClick} type="button">
      {children}
    </button>
  );
}
