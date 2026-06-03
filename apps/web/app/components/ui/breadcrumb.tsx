export function Breadcrumb({ trail }: { trail: string[] }) {
  return <div className="breadcrumb">{trail.map((item, index) => <span key={`${item}-${index}`}>{item}</span>)}</div>;
}
