import type { ResearchCatalog, ResearchPreviewResponse, ResearchVaultConfig, ResearchProposal, ResearchComparison } from '../types';
import { exactDecimal } from './orderView';
// Decimal movement is text-only; editable precision never passes through Number.
export function shiftDecimal(value: string, places: number): string {
  const match = /^([+-]?)(\d+)(?:\.(\d*))?$/.exec(value.trim());
  if (!match) return value;
  const digits = match[2] + (match[3] ?? ''), point = match[2].length + places;
  const text = point <= 0 ? `0.${'0'.repeat(-point)}${digits}`
    : point >= digits.length ? digits + '0'.repeat(point - digits.length)
    : `${digits.slice(0, point)}.${digits.slice(point)}`;
  const [whole, fraction] = text.split('.');
  return `${match[1]}${whole.replace(/^0+(?=\d)/, '')}${fraction ? '.' + fraction : ''}`;
}
export const researchFields = ['initial_equity_quote','paper_fee_model_enabled','paper_maker_fee_bps',
  'paper_taker_fee_bps','paper_funding_accounting_enabled','paper_funding_interval_seconds','max_capital_utilization'] as const;
export function isResearchConfig(value: unknown): value is ResearchVaultConfig {
  if (!value || typeof value !== 'object') return false;
  const x = value as Record<string, unknown>;
  return Object.keys(x).length === researchFields.length && researchFields.every(k => k in x)
    && ['initial_equity_quote','paper_maker_fee_bps','paper_taker_fee_bps','max_capital_utilization'].every(k =>
      typeof x[k] === 'string' && x[k].length <= 80 && /^\d+(?:\.\d+)?$/.test(x[k] as string))
    && typeof x.paper_fee_model_enabled === 'boolean' && typeof x.paper_funding_accounting_enabled === 'boolean'
    && [1,60,300,3600,28800,86400].includes(x.paper_funding_interval_seconds as number);
}
const fingerprint = (v: unknown) => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const strings = (v: unknown) => Array.isArray(v) && v.every(x => typeof x === 'string');
export function checkedCatalog(value: ResearchCatalog): ResearchCatalog {
  if (!value || value.simulated !== true || value.research_config_version !== 'phase14-v1' || !Array.isArray(value.presets)
    || !value.presets.length || new Set(value.presets.map(p => p?.preset_id)).size !== value.presets.length
    || !value.presets.every(p => p && typeof p.preset_id === 'string' && typeof p.name === 'string'
      && typeof p.description === 'string' && typeof p.version === 'string' && isResearchConfig(p.config)
      && fingerprint(p.config_fingerprint) && strings(p.limitations))) throw new Error('Malformed research preset catalog.');
  return value;
}
function canonicalDecimal(value: string) {
  const text = exactDecimal(value.trim());
  if (text === '—') return text;
  const [whole, fraction] = text.replace(/^\+/, '').split('.');
  const trimmed = fraction?.replace(/0+$/, '');
  return whole.replace(/^0+(?=\d)/, '') + (trimmed ? '.' + trimmed : '');
}
export function checkedPreview(value: ResearchPreviewResponse, proposal: ResearchProposal): ResearchPreviewResponse {
  if (!value || value.simulated !== true || value.validation_status !== 'VALID'
    || value.research_config_version !== 'phase14-v1' || value.selected_preset_id !== proposal.selected_preset_id
    || typeof value.customized !== 'boolean' || (value.selected_preset_version !== null && typeof value.selected_preset_version !== 'string')
    || !isResearchConfig(value.normalized_config) || !isResearchConfig(value.baseline_values)
    || !isResearchConfig(value.custom_values) || !fingerprint(value.config_fingerprint)
    || typeof value.illustrative_utilization_ceiling_quote !== 'string' || !/^\d+(?:\.\d+)?$/.test(value.illustrative_utilization_ceiling_quote)
    || !strings(value.warnings) || !strings(value.limitations) || !Array.isArray(value.changed_fields)
    || !value.changed_fields.every(d => d && researchFields.includes(d.field) && typeof d.units === 'string'
      && ['string','number','boolean'].includes(typeof d.old_value) && ['string','number','boolean'].includes(typeof d.new_value)
      && (d.difference === null || typeof d.difference === 'string'))) throw new Error('Malformed research preview; draft remains unvalidated.');
  if (!researchFields.every(k => typeof proposal.config[k] === 'string'
    ? canonicalDecimal(proposal.config[k] as string) === canonicalDecimal(value.normalized_config[k] as string)
    : proposal.config[k] === value.normalized_config[k]) || JSON.stringify(value.custom_values) !== JSON.stringify(value.normalized_config))
    throw new Error('Research preview does not match the submitted draft.');
  return value;
}

export function checkedComparison(value: ResearchComparison, scenario: string, frames: number, configFingerprint: string): ResearchComparison {
  const a = value?.baseline_result, b = value?.custom_result;
  if (!value || value.simulated !== true || value.research_config_version !== 'phase14-v1'
    || value.scenario !== scenario || value.frame_count !== frames || value.custom_config_fingerprint !== configFingerprint
    || !a || !b || !a.simulated || !b.simulated || !a.metrics || !b.metrics
    || a.metrics.frame_count !== frames || b.metrics.frame_count !== frames || !Array.isArray(a.trace) || !Array.isArray(b.trace)
    || !fingerprint(a.dataset_fingerprint) || a.dataset_fingerprint !== b.dataset_fingerprint
    || a.strategy_fingerprint !== b.strategy_fingerprint || a.engine_version !== b.engine_version
    || !value.baseline_provenance || !value.custom_provenance || !value.risk_state_counts || !value.comparison_deltas
    || !strings(value.limitations)) throw new Error('Malformed or incompatible research comparison.');
  return value;
}
