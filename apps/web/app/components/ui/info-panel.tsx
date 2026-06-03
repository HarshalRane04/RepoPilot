import type { ReactNode } from "react";

export function InfoPanel({ number, title, children }: { number: string; title: string; children: ReactNode }) {
  return (
    <section className="panel infoPanel">
      <h2><span>{number}.</span> {title}</h2>
      {children}
    </section>
  );
}
