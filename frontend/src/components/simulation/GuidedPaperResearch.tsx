import type { ReactNode } from 'react';

export const guidedPaperScenarios = ['QUIET', 'TREND_UP', 'HIGH_VOLATILITY', 'LIQUIDITY_SHOCK'];

export function GuidedPaperStep({ guided, step, title, children }: {
  guided: boolean; step: number; title: string; children: ReactNode;
}) {
  return <div className={guided ? 'guidedPaperStep' : undefined}>
    {guided && <h3>Step {step} · {title}</h3>}
    {children}
  </div>;
}
