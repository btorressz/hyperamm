import { assetDecimalFields, assetFamilies, assetModels } from '../../types/assetAmm';
import type { AssetAmmResearchControls, AssetControlInputs, AssetDecimalField, AssetFamily } from '../../types/assetAmm';
import type { GeneralizedPaperResult } from '../../types/generalizedPaper';
import type { MarketUniverseMetadata } from '../../types/marketUniverse';
import { assetDecimalKeys } from '../../utils/assetAmm';
import { accountingValue } from '../../utils/researchEvidence';

export interface AssetDraft {
  family: AssetFamily;
  minimum: string;
  overrides: Partial<Record<keyof AssetControlInputs, string>>;
}

export const initialAssetDraft: AssetDraft = { family: 'UNKNOWN', minimum: '100', overrides: {} };
const primaryFields = ['max_distance_bps', 'base_order_size', 'total_liquidity'] as const;
const advancedFields = assetDecimalKeys.filter(key => !primaryFields.some(primary => primary === key));

export function PaperAssetConfiguration({ draft, defaults, record, loading, error, advisory, onChange, onRemoveAdvisory }: {
  draft: AssetDraft;
  defaults?: AssetAmmResearchControls;
  record?: MarketUniverseMetadata;
  loading: boolean;
  error: string;
  advisory?: string;
  onChange: (next: AssetDraft) => void;
  onRemoveAdvisory: () => void;
}) {
  const control = (key: keyof AssetControlInputs) => String(draft.overrides[key] ?? defaults?.[key] ?? '');
  const update = (key: keyof AssetControlInputs, value: string) =>
    onChange({ ...draft, overrides: { ...draft.overrides, [key]: value } });
  const input = (key: AssetDecimalField | 'levels_per_side', label: string) =>
    <label key={key}>{label}
      <input inputMode={key === 'levels_per_side' ? 'numeric' : 'decimal'}
        maxLength={key === 'levels_per_side' ? 2 : 80} value={control(key)} onChange={e => update(key, e.target.value)} />
    </label>;

  return <fieldset className="paperRiskFieldset" aria-describedby="asset-amm-classification">
    <legend>Asset-aware AMM configuration</legend>
    <p id="asset-amm-classification">The asset family is an operator-declared research label. Exchange discovery supplies the market identity and precision. Strategy settings are hypothetical.</p>
    <p>Check PAPER eligibility to test quote precision, minimum order notional and any enabled risk model.</p>
    {record && <p>Discovered size precision (szDecimals) {record.sz_decimals}. Research prices use a magnitude-dependent decimal grid with up to five significant figures for noninteger prices and at most {6 - record.sz_decimals} decimal places. Exchange tick calibration is unverified.</p>}
    <div className="researchFilters">
      <label>Research asset family
        <select value={draft.family} onChange={e => onChange({ ...draft, family: e.target.value as AssetFamily })}>
          {Object.entries(assetFamilies).map(([family, label]) => <option key={family} value={family}>{label}</option>)}
        </select>
      </label>
      <label>AMM model
        <select value={control('amm_model')} onChange={e => update('amm_model', e.target.value)}>
          <option value="" disabled>Server default</option>
          {Object.entries(assetModels).map(([model, label]) => <option key={model} value={model}>{label}</option>)}
        </select>
      </label>
      {input('levels_per_side', 'Levels per side')}
      {primaryFields.map(key => input(key, assetDecimalFields[key][0]))}
      <label>Minimum research order notional (hypothetical quote units)
        <input inputMode="decimal" maxLength={24} value={draft.minimum}
          onChange={e => onChange({ ...draft, minimum: e.target.value })} />
      </label>
    </div>
    <details>
      <summary>Advanced AMM Research Settings</summary>
      <div className="researchFilters">{advancedFields.map(key => input(key, assetDecimalFields[key][0]))}</div>
      <button type="button" disabled={!Object.keys(draft.overrides).length}
        onClick={() => onChange({ ...draft, overrides: {} })}>Restore server AMM defaults</button>
    </details>
    {loading && <p role="status">Loading asset AMM defaults…</p>}
    {error && <p role="alert">{error}</p>}
    {advisory && <p>Attached advisory evidence <code>{advisory}</code>{' '}
      <button type="button" onClick={onRemoveAdvisory}>Remove advisory reference</button>
    </p>}
  </fieldset>;
}

export function PaperAssetEvidence({ result }: { result: GeneralizedPaperResult }) {
  const policy = result.proposal.asset_amm_policy;
  if (!policy) return null;
  const { controls } = policy;
  return <details>
    <summary>Asset-aware AMM configuration and provenance</summary>
    <dl className="researchDetails">
      <div><dt>Declared research family</dt><dd>{assetFamilies[policy.classification.family]}</dd></div>
      <div><dt>AMM model</dt><dd>{assetModels[controls.amm_model]}</dd></div>
      <div><dt>Levels per side</dt><dd>{controls.levels_per_side}</dd></div>
      <div><dt>Discovered szDecimals</dt><dd>{policy.metadata.sz_decimals}</dd></div>
      <div><dt>Minimum research order notional</dt><dd>{accountingValue(result.proposal.minimum_order_notional)} hypothetical quote units</dd></div>
      {assetDecimalKeys.map(key => <div key={key}><dt>{assetDecimalFields[key][0]}</dt><dd>{controls[key]}</dd></div>)}
      <div><dt>Research policy fingerprint</dt><dd><code>{result.admission.binding.asset_policy_fingerprint}</code></dd></div>
      <div><dt>Mapped strategy fingerprint</dt><dd><code>{result.result.strategy_fingerprint}</code></dd></div>
      <div><dt>Metadata source</dt><dd>{policy.metadata.identity.dex ? 'Official HIP-3 metadata' : 'Official Core metadata'}</dd></div>
      {policy.advisory_snapshot_fingerprint && <div><dt>Advisory snapshot fingerprint</dt>
        <dd><code>{policy.advisory_snapshot_fingerprint}</code></dd></div>}
    </dl>
    <p>PAPER only. The scenario uses a synthetic price path and book depth, as well as hypothetical capital and economics.
      The operator declares the asset family. Exchange calibration is unverified. The result grants no trading authority and offers no guarantee of profit.</p>
  </details>;
}
