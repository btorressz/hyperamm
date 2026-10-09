import type { Quote } from "../types";
import { effectiveLiquidity } from "../utils/effectiveLiquidity";

export function EffectiveLiquidity({ quotes, configured, stage = "Authorized" }: {
  quotes: Quote[]; configured?: number; stage?: string;
}) {
  const depth = effectiveLiquidity(quotes);
  if (!depth.available) return <p className="muted">Effective liquidity unavailable: invalid quote evidence.</p>;
  return <div className="panelNote">
    <p>{configured != null && <>Configured levels per side: {configured} · </>}
      {stage} quote slots: {depth.logical_slots} · Distinct BID prices: {depth.effective_bid_levels} ·
      Distinct ASK prices: {depth.effective_ask_levels}</p>
    {depth.warnings.map(w => <p className="alert" key={w}>{w}</p>)}
    <small>Grouped quote depth is observational. Resting venue quantities require separate order-status evidence.</small>
  </div>;
}
