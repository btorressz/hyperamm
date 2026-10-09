import type { TerminalState } from "../types";
import { StrategyControls } from "../components/StrategyControls";
import { EffectiveLiquidity } from "../components/EffectiveLiquidity";
export function AmmSettings({ t }: { t: TerminalState }) {
  return (
    <div className="stack">
      <h1>AMM Settings</h1>
      <p className="muted">
        Advanced configuration is validated by the existing strategy API.
      </p>
      <StrategyControls t={t} />
      <EffectiveLiquidity quotes={t.authorized_quotes} configured={t.strategy.config.levels_per_side} />
    </div>
  );
}
