import type { KeyboardEvent, MouseEvent, ReactNode } from "react";

interface ClickableRowProps {
  onClick: () => void;
  className: string;
  children: ReactNode;
  disabled?: boolean;
}

export function ClickableRow({ onClick, className, children, disabled }: ClickableRowProps) {
  return (
    <div
      className={className}
      role="row"
      tabIndex={disabled ? undefined : 0}
      aria-disabled={disabled}
      onClick={disabled ? undefined : onClick}
      onKeyDown={(e: KeyboardEvent<HTMLDivElement>) => {
        if (disabled) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
    >
      {children}
    </div>
  );
}
