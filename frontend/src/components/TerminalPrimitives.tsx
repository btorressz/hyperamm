import type { ReactNode } from "react";
export function Panel({
  title,
  meta,
  children,
  className = "",
}: {
  title: string;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panelHead">
        <b>{title}</b>
        <span>{meta}</span>
      </div>
      {children}
    </section>
  );
}
export function Metrics({ items }: { items: Array<[string, ReactNode]> }) {
  return (
    <div className="terminalMetrics">
      {items.map(([label, value]) => (
        <div key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return <p className="emptyEvidence">{children}</p>;
}
