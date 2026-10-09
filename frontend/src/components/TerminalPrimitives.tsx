import { useId, type ReactNode } from "react";
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
  const titleId = useId();
  return (
    <section className={`panel ${className}`} aria-labelledby={titleId}>
      <div className="panelHead">
        <h2 id={titleId}>{title}</h2>
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

export function Loading({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="loading panel" role="status" aria-live="polite">
      <h2>{title}</h2>
      <p>{children}</p>
    </section>
  );
}

export function StatusBanner({
  children,
  tone = "warn",
}: {
  children: ReactNode;
  tone?: "warn" | "bad";
}) {
  return (
    <div
      className={`alert ${tone === "bad" ? "dangerText" : ""}`}
      role={tone === "bad" ? "alert" : "status"}
    >
      {children}
    </div>
  );
}
