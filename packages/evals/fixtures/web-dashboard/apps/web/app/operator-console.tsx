import { modeLabel, type Readiness } from "../lib/api";

export function OperatorConsole({ readiness }: { readiness: Readiness }) {
  return `<section>${modeLabel(readiness)}</section>`;
}

