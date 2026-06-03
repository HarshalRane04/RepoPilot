export function ScreenHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="screenHeader">
      <h1>{title}</h1>
      {subtitle ? <p>{subtitle}</p> : null}
    </div>
  );
}
