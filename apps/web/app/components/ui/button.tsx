import type { ReactNode } from "react";

type ButtonVariant = "primary" | "ghost" | "danger" | "cyan" | "row";

export function Button({
  variant = "ghost",
  children,
  disabled,
  icon,
  onClick,
  type = "button",
  wide
}: {
  variant?: ButtonVariant;
  children: ReactNode;
  disabled?: boolean;
  icon?: ReactNode;
  onClick?: () => void;
  type?: "button" | "submit" | "reset";
  wide?: boolean;
}) {
  const classes = buttonClass(variant, wide);
  return (
    <button className={classes} disabled={disabled} onClick={onClick} type={type}>
      {icon}
      {children}
    </button>
  );
}

function buttonClass(variant: ButtonVariant, wide?: boolean) {
  const base = wide ? "wide" : "";
  switch (variant) {
    case "primary":
      return `primaryAction ${base}`;
    case "danger":
      return `dangerAction ${base}`;
    case "cyan":
      return `cyanAction ${base}`;
    case "row":
      return "rowAction";
    case "ghost":
    default:
      return `ghostAction ${base}`;
  }
}

export function PrimaryAction({ children, disabled, icon, onClick, type = "button", wide }: Omit<Parameters<typeof Button>[0], "variant">) {
  return <Button variant="primary" disabled={disabled} icon={icon} onClick={onClick} type={type} wide={wide}>{children}</Button>;
}

export function GhostAction({ children, disabled, icon, onClick, type = "button", wide }: Omit<Parameters<typeof Button>[0], "variant">) {
  return <Button variant="ghost" disabled={disabled} icon={icon} onClick={onClick} type={type} wide={wide}>{children}</Button>;
}

export function DangerAction({ children, disabled, icon, onClick, type = "button", wide }: Omit<Parameters<typeof Button>[0], "variant">) {
  return <Button variant="danger" disabled={disabled} icon={icon} onClick={onClick} type={type} wide={wide}>{children}</Button>;
}

export function CyanAction({ children, disabled, icon, onClick, type = "button", wide }: Omit<Parameters<typeof Button>[0], "variant">) {
  return <Button variant="cyan" disabled={disabled} icon={icon} onClick={onClick} type={type} wide={wide}>{children}</Button>;
}

export function RowAction({ children, disabled, icon, onClick, type = "button" }: Omit<Parameters<typeof Button>[0], "variant" | "wide">) {
  return <Button variant="row" disabled={disabled} icon={icon} onClick={onClick} type={type}>{children}</Button>;
}
