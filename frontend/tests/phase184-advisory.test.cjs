const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const path = require('node:path');
const test = require('node:test');
const { checkedAdvisoryResponse } = require(path.join(process.env.TERMINAL_TEST_BUILD, 'utils/advisory.js'));

const version = { contract_version: 'phase184a-v1' };
const readOnly = { ...version, read_only: true, authority: 'NONE', execution_eligible: false };
const neutral = { ...readOnly, affects_quotes: false, can_override_risk: false, can_authorize_paper: false };
const analysis_version = 'phase184bcd-v1';
const scope = 'SINGLE_MARKET_RESEARCH_ONLY';
const identity = { contract_version: 'phase180b-v2', venue: 'HYPERLIQUID', network: 'MAINNET',
  instrument_type: 'HIP3_PERP', dex: 'xyz', instrument_name: 'GOLD' };
const observed_at = '2026-11-19T10:00:00.000001Z';
const evaluated_at = '2026-11-19T10:00:05.000004Z';
const valid_until = '2026-11-19T10:00:10.000005Z';
const canonical = value => value && typeof value === 'object' && !Array.isArray(value)
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]))
  : Array.isArray(value) ? value.map(canonical) : value;
const digest = value => createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');
const metadata = { contract_version: identity.contract_version, identity, source_coin: 'xyz:GOLD', universe_index: 0,
  sz_decimals: 3, listed: true, metadata_status: 'EXCHANGE_VERIFIED', metadata_source: 'OFFICIAL_SDK_HIP3_META', observed_at };
const catalog_fingerprint = digest('catalog');
const request = { identity, catalog_fingerprint, operation: 'FUNDING_BASIS' };
const selection = { metadata, catalog_fingerprint, metadata_fingerprint: digest(metadata), max_age_seconds: 60 };

function seal(value) {
  for (const advice of Object.values(value.snapshot).filter(item => item?.agent))
    advice.context_fingerprint = digest(value.snapshot.context);
  value.snapshot_fingerprint = digest(value.snapshot);
  return value;
}

function fundingFixture() {
  const point = (category, unit, providerClock = false) => ({ ...readOnly, identity, category,
    unit, source_id: providerClock ? 'HYPERLIQUID_L2_BOOK' : 'HYPERLIQUID_META_AND_ASSET_CTXS',
    captured_at: observed_at, observed_at: providerClock ? observed_at : null, scenario_at: null,
    observation_clock: providerClock ? 'PROVIDER_EVENT' : 'LOCAL_RECEIPT',
    valid_until, binding_version: analysis_version, source_fingerprint: digest(category),
    provenance: 'EXCHANGE_OBSERVED', financial_unit: null,
  });
  const sources = [
    point('FUNDING', 'RATE_PER_HOUR'), point('MARK_PRICE', 'PRICE_QUOTE_PER_BASE'),
    point('ORACLE_PRICE', 'PRICE_QUOTE_PER_BASE'), point('MID_PRICE', 'PRICE_QUOTE_PER_BASE', true),
  ];
  const finding = { ...neutral, identity, evaluated_at, analysis_version, status: 'READY', confidence: '0.9',
    provenance: 'EXCHANGE_OBSERVED', source_fingerprints: sources.map(source => source.source_fingerprint),
    reasons: ['Current hourly public evidence.'], missing_requirements: ['FUNDING_HISTORY'] };
  return seal(structuredClone({
    ...neutral, schema_version: 'phase184e-v1', identity, evaluated_at, valid_until, funding_mode: 'OBSERVED',
    paper_result_fingerprint: null, quote_cohorts: [], quote_sequence: null, quote_risk_state: null, issues: [],
    snapshot: { ...version, authority: 'NONE', execution_eligible: false, affects_quotes: false, scope,
      context: { ...readOnly, scope, metadata, catalog_fingerprint, metadata_fingerprint: selection.metadata_fingerprint,
        paper_binding_fingerprint: null, risk_model_fingerprint: null, evaluated_at, valid_until, sources },
      market_eligibility: { ...finding, agent: 'MARKET_ELIGIBILITY', operation: 'FUNDING_BASIS', suitability: 'CONDITIONAL' },
      funding_basis: { ...finding, agent: 'FUNDING_BASIS', state: 'FUNDING_NEGATIVE', funding_rate: '-1E-5',
        funding_interval_seconds: 3600, mark_price: '100.01', oracle_price: '100', midpoint_price: '100.02',
        mark_oracle_basis_bps: '1', mark_mid_basis_bps: '-0.99980004', oracle_mid_basis_bps: '-1.99960008',
        funding_convention: 'HYPERLIQUID_HOURLY', funding_direction: 'SHORTS_PAY', history_count: 0 },
      quote_economics: null,
    },
  }));
}

const validate = payload => checkedAdvisoryResponse(payload, request, selection);
test('Phase 18.4 validates a versioned quote-free observed snapshot with two source clocks', async () => {
  const wire = fundingFixture();
  assert.deepEqual(await validate(wire), wire);
});

for (const [rate, direction, state] of [['0.005', 'LONGS_PAY', 'FUNDING_POSITIVE'], ['-0.005', 'SHORTS_PAY', 'FUNDING_NEGATIVE']]) {
  test(`Phase 18.4 accepts the exact public funding boundary ${rate}`, async () => {
    const wire = fundingFixture();
    Object.assign(wire.snapshot.funding_basis, { funding_rate: rate, funding_direction: direction, state });
    assert.deepEqual(await validate(seal(wire)), wire);
  });
}

for (const [name, change, reseal = true] of [
  ['authority escalation', value => { value.snapshot.funding_basis.can_override_risk = true; }],
  ['unknown analysis version', value => { value.snapshot.funding_basis.analysis_version = 'phase184x'; }],
  ['wrong network', value => { value.snapshot.context.sources[0].identity.network = 'TESTNET'; }],
  ['wrong DEX', value => { value.snapshot.context.sources[0].identity.dex = 'abc'; }],
  ['stale source at publication', value => { value.snapshot.context.sources[0].valid_until = '2026-11-19T10:00:08Z'; }],
  ['wrong market generation', value => { value.snapshot.context.catalog_fingerprint = digest('another'); }],
  ['future provider event', value => { value.snapshot.context.sources[3].observed_at = value.evaluated_at; }],
  ['receipt impersonating event time', value => { value.snapshot.context.sources[0].observed_at = observed_at; }],
  ['synthetic promotion', value => { value.snapshot.context.sources[0].provenance = 'SCENARIO_SYNTHETIC'; }],
  ['wrong evidence unit', value => { value.snapshot.context.sources[0].unit = 'PAPER_QUOTE_PER_BASE'; }],
  ['excess public hourly funding with a valid fingerprint', value => {
    value.snapshot.funding_basis.funding_rate = '-0.005000000001';
  }],
  ['wrong funding interval', value => { value.snapshot.funding_basis.funding_interval_seconds = 1; }],
  ['wrong funding sign', value => { value.snapshot.funding_basis.funding_direction = 'LONGS_PAY'; }],
  ['number instead of Decimal string', value => { value.snapshot.funding_basis.mark_price = 100; }],
  ['out-of-range confidence', value => { value.snapshot.funding_basis.confidence = '1.01'; }],
  ['unknown source digest', value => { value.snapshot.funding_basis.source_fingerprints[0] = digest('other'); }],
  ['unknown response issue', value => { value.issues.push('READY_OVERRIDE'); }],
  ['changed financial output with retained fingerprint', value => { value.snapshot.funding_basis.mark_price = '100.02'; }, false],
]) {
  test(`Phase 18.4 rejects ${name}`, async () => {
    const value = fundingFixture();
    // Individual evidence identities are independent on the JSON wire.
    value.snapshot.context.sources = value.snapshot.context.sources.map(source => ({ ...source, identity: { ...source.identity } }));
    change(value);
    await assert.rejects(validate(reseal ? seal(value) : value), /Invalid or/);
  });
}

function quoteFixture() {
  const paper = { result_fingerprint: digest('paper-result'),
    binding: { catalog_fingerprint, metadata_fingerprint: selection.metadata_fingerprint,
      profile_fingerprint: digest('profile'), configuration_fingerprint: digest('paper-configuration') } };
  const quote = { sequence: 3, assumptions: { holding_seconds: 10, closing_liquidity: 'MAKER',
    exit_slippage_bps: '1', inventory_rate_bps: '1' } };
  const input = { ...request, operation: 'QUOTE_ECONOMICS', paper_receipt: digest('receipt'), quote };
  const unit = { contract_version: 'phase183a-v1', network: 'MAINNET', kind: 'HYPOTHETICAL_QUOTE',
    symbol: 'HYPOTHETICAL_QUOTE', asset_namespace: '', asset_reference: null, provenance: 'RESEARCH_ASSUMPTION' };
  const sources = [
    ['QUOTE_LADDER', 'PAPER_SUBMITTED_QUOTES'], ['PAPER_FILLS', 'PAPER_EXECUTION_RECEIPTS'],
    ['FILL_MARKOUT', 'PAPER_MATURE_MARKOUT'], ['FUNDING', 'PAPER_QUOTE_CARRY'],
    ['FEES', 'ASSUMPTION_PAPER_FEES'], ['INVENTORY', 'ASSUMPTION_PAPER_INVENTORY'],
  ].map(([category, source_id]) => ({
    ...readOnly, identity, category, source_id, captured_at: observed_at, observed_at: null,
    scenario_at: source_id.startsWith('PAPER_') ? '2026-01-01T00:00:00Z' : null,
    valid_until, binding_version: analysis_version, source_fingerprint: digest(category),
    provenance: source_id.startsWith('PAPER_') ? 'SCENARIO_SYNTHETIC' : 'HYPOTHETICAL_ASSUMPTION',
    ...(category === 'FUNDING' ? { unit: 'MARK_NOTIONAL_RATE_PER_PAPER_INTERVAL', financial_unit: null } : { financial_unit: unit }),
  }));
  const wire = fundingFixture();
  const { market_eligibility: eligibility } = wire.snapshot;
  Object.assign(eligibility, { operation: 'QUOTE_ECONOMICS', provenance: 'SCENARIO_SYNTHETIC',
    reasons: ['Attributed synthetic references.'], missing_requirements: [], source_fingerprints: [sources[0].source_fingerprint] });
  Object.assign(wire, { funding_mode: null, paper_result_fingerprint: paper.result_fingerprint,
    quote_cohorts: [1, 3, 120], quote_sequence: 3, quote_risk_state: 'NORMAL' });
  Object.assign(wire.snapshot.context, { sources, paper_binding_fingerprint: paper.binding.configuration_fingerprint });
  wire.snapshot.funding_basis = null;
  wire.snapshot.quote_economics = { ...eligibility, agent: 'QUOTE_ECONOMICS', provenance: 'MIXED', state: 'MODELED_POSITIVE',
    source_fingerprints: sources.map(source => source.source_fingerprint), hypothetical_only: true, guarantees_profit: false,
    accounting_unit: unit, gross_spread_bps: '100', captured_spread_bps: '3', modeled_edge_bps: '1',
    fee_cost_bps: '2', funding_cost_bps: '-1', inventory_cost_bps: '1', adverse_selection_cost_bps: '0',
    slippage_cost_bps: '0', break_even_capture_bps: '2', bid_capture_bps: '3', fill_coverage: 'ONE_SIDED',
    submitted_bid: '100', submitted_ask: '101', entry_fees_quote: '0.01', exit_fees_quote: '0.01',
    quoted_notional: '201', executed_reference_notional: '100.03', filled_base: '1', residual_base: '1',
    inventory_expansion_base: '1', holding_seconds: 10, funding_interval_seconds: 1,
    attributed_fill_count: 1, matured_markout_count: 1,
  };
  delete wire.snapshot.quote_economics.operation;
  delete wire.snapshot.quote_economics.suitability;
  return { wire: seal(wire), input, paper };
}

test('Phase 18.4 validates reconciled synthetic quote economics and the last supported frame number', async () => {
  const { wire, input, paper } = quoteFixture();
  assert.deepEqual(await checkedAdvisoryResponse(wire, input, selection, paper), wire);
});

for (const [name, change] of [
  ['altered modeled edge', wire => { wire.snapshot.quote_economics.modeled_edge_bps = '2'; }],
  ['missing cost', wire => { delete wire.snapshot.quote_economics.adverse_selection_cost_bps; }],
  ['wrong fee denomination', wire => { wire.snapshot.quote_economics.accounting_unit.network = 'TESTNET'; }],
  ['wrong cost assumptions', wire => { wire.snapshot.quote_economics.holding_seconds = 11; }],
  ['false markout maturity', wire => { wire.snapshot.quote_economics.matured_markout_count = 0; }],
  ['modeled edge after HALT', wire => { wire.quote_risk_state = 'HALT'; }],
]) {
  test(`Phase 18.4 rejects ${name} even with a fresh digest`, async () => {
    const { wire, input, paper } = quoteFixture();
    change(wire);
    await assert.rejects(checkedAdvisoryResponse(seal(wire), input, selection, paper), /Invalid or/);
  });
}
