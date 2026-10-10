import type { ResearchPreset } from '../../types';
import { shiftDecimal } from '../../utils/researchVault';
export function ResearchPresets({ presets, selected, onSelect }: {
  presets: ResearchPreset[]; selected: string | null; onSelect: (preset: ResearchPreset) => void;
}) {
  return <section aria-label="Research preset library" className="researchPresetGrid">{presets.map(p =>
    <button key={p.preset_id} type="button" className="researchPreset researchInset" aria-pressed={selected === p.preset_id}
      onClick={() => onSelect(p)}>
      <strong>{p.name}</strong><span>{p.description}</span>
      <span>Starting capital: {p.config.initial_equity_quote} quote</span>
      <span>Fees: {p.config.paper_fee_model_enabled ? `${p.config.paper_maker_fee_bps} / ${p.config.paper_taker_fee_bps} bps maker / taker` : 'configured zero fees'}</span>
      <span>Funding: {p.config.paper_funding_accounting_enabled ? `sampled every ${p.config.paper_funding_interval_seconds} seconds` : 'configured zero funding'}</span>
      <span>Utilization cap: {shiftDecimal(p.config.max_capital_utilization, 2)}% · preset v{p.version}</span>
    </button>)}</section>;
}
