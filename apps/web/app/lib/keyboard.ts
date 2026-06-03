import type { KeyboardEvent } from "react";

export type RowClick = (
  event: KeyboardEvent<HTMLElement> | React.MouseEvent<HTMLElement, MouseEvent>
) => void;

export function rowKeyboard(onClick: RowClick, disabled?: boolean) {
  return {
    role: "row",
    tabIndex: disabled ? undefined : (0 as const),
    "aria-disabled": disabled ? true : undefined,
    onKeyDown: (event: KeyboardEvent<HTMLElement>) => {
      if (disabled) return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onClick(event);
      }
    }
  };
}

export function genericKeyboard(onClick: () => void, disabled?: boolean) {
  return {
    tabIndex: disabled ? undefined : (0 as const),
    "aria-disabled": disabled ? true : undefined,
    onKeyDown: (event: KeyboardEvent<HTMLElement>) => {
      if (disabled) return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onClick();
      }
    }
  };
}
