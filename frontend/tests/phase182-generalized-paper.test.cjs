const assert = require('node:assert/strict');
const test = require('node:test');
const path = require('node:path');
const load = name => require(path.join(process.env.TERMINAL_TEST_BUILD, name));
const { api } = load('api/client.js');
const { paperEvidenceBoundary } = load('types/generalizedPaper.js');
const { checkedPaperAdmission, checkedPaperResult, paperAdmissionIsCurrent } = load('utils/generalizedPaper.js');
const { marketUniverseKey } = load('utils/marketUniverse.js');
const { assetControlInput, assetMinimumNotional, assetReferenceIsValid, checkedAssetPolicyPreview } = load('utils/assetAmm.js');
const { researchFingerprint } = load('utils/researchFingerprint.js');

const profile_version = 'phase182-v1';
const contract_version = 'phase180b-v2';
const identity = { contract_version, venue: 'HYPERLIQUID', network: 'MAINNET', dex: 'xyz',
  instrument_type: 'HIP3_PERP', instrument_name: 'GOLD' };
const observed_at = '2026-11-18T20:00:00.000001Z';
const evaluated_at = '2026-11-18T20:00:12.000001Z';
const valid_until = '2026-11-18T20:01:00.000001Z';
const limitations = ['local', 'synthetic', 'hypothetical', 'unverified', 'no authority'];
const binding = { metadata_fingerprint: 'a'.repeat(64), profile_fingerprint: 'b'.repeat(64),
  configuration_fingerprint: 'c'.repeat(64), catalog_fingerprint: '1'.repeat(64) };
const proposal = { profile_version, identity, simulated_reference_price: '2.500e3', scenario: 'FLASH_MOVE',
  frames: 40, trace_max_points: 10, economics: { model: 'HYPOTHETICAL_LINEAR' } };
const economics = { ...proposal.economics, maker_fee_bps: '0', taker_fee_bps: '0', funding_interval_seconds: null };

function admission() {
  return structuredClone({ profile_version, identity, evaluated_at, valid_until, status: 'ELIGIBLE', reason: 'ADMITTED',
    scope: 'LOCAL_PAPER_ONLY', authority: 'NONE', execution_eligible: false, explanation: 'Local PAPER only.',
    checks: [], limitations, binding,
    profile: { profile_version, limitations, stable_key: marketUniverseKey(identity), exchange_coin: 'xyz:GOLD',
      metadata_fingerprint: binding.metadata_fingerprint, profile_fingerprint: binding.profile_fingerprint,
      model_compatibility: 'HYPOTHETICAL_LINEAR_ONLY', paper_eligibility: 'REQUIRES_ADMISSION',
      evidence_boundary: paperEvidenceBoundary,
      authority: 'NONE', execution_eligible: false, reference_source: 'USER_SUPPLIED_SYNTHETIC',
      simulated_reference_price: '2500', synthetic_top_depth_quote: '18000', economics,
      discovery: { contract_version, identity, metadata_fingerprint: binding.metadata_fingerprint, evaluated_at,
        read_only: true, authority: 'NONE', paper_research_eligible: false, execution_eligible: false,
        discovery_eligible: true, reason: 'DISCOVERABLE' },
      metadata: { contract_version, identity, universe_index: 0, source_coin: 'xyz:GOLD', sz_decimals: 2, listed: true,
        metadata_status: 'EXCHANGE_VERIFIED', metadata_source: 'OFFICIAL_SDK_HIP3_META', observed_at } } });
}

function rejection(reason, check, unavailable = false) {
  return { ...admission(), status: unavailable ? 'UNAVAILABLE' : 'REJECTED', reason, checks: [check],
    valid_until: null, binding: null, explanation: 'Review the evidence.' };
}

function result() {
  const market = marketUniverseKey(identity);
  return { profile_version, admission: admission(), simulated: true, execution_mode: 'PAPER',
    result_fingerprint: 'd'.repeat(64), started_at: '2026-11-18T20:00:13Z',
    proposal: { ...proposal, economics, minimum_order_notional: '100', synthetic_top_depth_quote: '18000' },
    result: { engine_version: 'phase10-v1', run_fingerprint: 'e'.repeat(64), dataset_fingerprint: 'f'.repeat(64),
      strategy_fingerprint: '0'.repeat(64), scenario: proposal.scenario, research_market: market,
      market_profile_version: profile_version, market_profile_fingerprint: binding.profile_fingerprint, simulated: true,
      metrics: { frame_count: 40, fill_count: 4 },
      vault: { market, mode: 'PAPER', simulated: true, net_pnl_quote: '-12.95001', fees_quote: '0',
        funding_quote: '0', position_base: '1.2500', initial_equity_quote: '10000',
        equity_quote: '9987.04999', reserved_capital_quote: '1300',
        realized_pnl_quote: '0', unrealized_pnl_quote: '-12.95001' } } };
}

async function assetFixture() {
  const dec = admission();
  const metadata = dec.profile.metadata;
  const fingerprint = await researchFingerprint(metadata);
  dec.profile.metadata_fingerprint = dec.profile.discovery.metadata_fingerprint = dec.binding.metadata_fingerprint = fingerprint;
  const selection = { metadata, metadata_fingerprint: fingerprint,
    catalog_fingerprint: binding.catalog_fingerprint, max_age_seconds: 60 };
  const request = { profile_version, identity, family: 'UNKNOWN', catalog_fingerprint: selection.catalog_fingerprint,
    simulated_reference_price: '2500', minimum_order_notional: '100', controls: { levels_per_side: 2, max_distance_bps: '1e2' } };
  const flags = { contract_version: 'phase185a-v1', authority: 'NONE', read_only: true, risk_ready: false,
    affects_quotes: false, can_override_risk: false, execution_eligible: false };
  const policy = { ...flags, metadata, metadata_fingerprint: fingerprint, catalog_fingerprint: selection.catalog_fingerprint,
    classification: { contract_version: flags.contract_version, family: request.family, provenance: 'OPERATOR_DECLARED_RESEARCH',
      exchange_class_verified: false, tradability_verified: false },
    controls: { contract_version: flags.contract_version, provenance: 'HYPOTHETICAL_RESEARCH_SETTINGS',
      price_precision_policy: 'REUSE_GENERALIZED_PRECISION', size_precision_policy: 'REUSE_DISCOVERED_SZ_DECIMALS',
      amm_model: 'CONSTANT_PRODUCT', levels_per_side: 2, max_distance_bps: '100', base_order_size: '0.1',
      total_liquidity: '0.5', virtual_base_reserve: '120', virtual_quote_reserve: '300000',
      concentration_factor: '8', concentration_lower_bps: '10', concentration_upper_bps: '200',
      target_inventory_base: '0', soft_inventory_limit_base: '2', hard_inventory_limit_base: '4',
      max_inventory_price_skew_bps: '20', volatility_spread_strength: '1', volatility_size_strength: '0.5',
      max_funding_reference_shift_bps: '5' },
    hypothetical_accounting_unit: { contract_version: 'phase183a-v1', network: identity.network,
      kind: 'HYPOTHETICAL_QUOTE', symbol: 'HYPOTHETICAL_QUOTE', asset_namespace: '',
      asset_reference: null, provenance: 'RESEARCH_ASSUMPTION' },
    simulated_reference_price: '2500', declared_at: evaluated_at, research_risk_fingerprint: null,
    advisory_snapshot_fingerprint: null, reference_provenance: 'USER_SUPPLIED_SYNTHETIC',
    source_provenance: 'DECLARED_HYPOTHETICAL_POLICY', research_scope: 'SINGLE_MARKET_RESEARCH_ONLY',
    execution_mode: 'PAPER', can_authorize_paper: false };
  const assessment = { ...flags, identity, metadata_fingerprint: fingerprint,
    policy_fingerprint: await researchFingerprint(policy), evaluated_at, status: 'RESEARCH_DRAFT', reason: 'DISCOVERABLE',
    eligible_for_paper: false, eligible_for_testnet: false, eligible_for_live: false };
  dec.binding.asset_policy_fingerprint = assessment.policy_fingerprint;
  return { request, selection, draft: structuredClone({ policy, assessment }), dec };
}

test('asset research verifies server draft then the same policy in admission and result', async () => {
  const { draft, request, selection, dec } = await assetFixture();
  const { policy, assessment } = await checkedAssetPolicyPreview(draft, request, selection);
  const admitted = { ...proposal, asset_amm_policy: policy };
  assert.equal(checkedPaperAdmission(dec, admitted, assessment.policy_fingerprint), dec);
  const evidence = result();
  evidence.admission = dec;
  evidence.proposal.asset_amm_policy = structuredClone(policy);
  assert.equal(checkedPaperResult(evidence, admitted, dec.binding, assessment.policy_fingerprint), evidence);
  evidence.proposal.asset_amm_policy.controls.max_distance_bps = '101';
  assert.throws(() => checkedPaperResult(evidence, admitted, dec.binding, assessment.policy_fingerprint), /Invalid or unsupported/);
  assert.throws(() => checkedPaperAdmission(dec, proposal), /Invalid or unsupported/);
  dec.binding.asset_policy_fingerprint = 'f'.repeat(64);
  assert.throws(() => checkedPaperAdmission(dec, admitted, assessment.policy_fingerprint), /Invalid or unsupported/);
});

for (const [label, mutate] of [
  ['contract version', w => { w.policy.contract_version = 'phase999'; }],
  ['market metadata', w => { w.policy.metadata.identity.dex = 'other'; }],
  ['network', w => { w.policy.metadata.identity.network = 'TESTNET'; }],
  ['metadata digest', w => { w.policy.metadata_fingerprint = '0'.repeat(64); }],
  ['catalog digest', w => { w.policy.catalog_fingerprint = '0'.repeat(64); }],
  ['taxonomy', w => { w.policy.classification.exchange_class_verified = true; }],
  ['family', w => { w.policy.classification.family = 'UNDECLARED'; }],
  ['AMM model', w => { w.policy.controls.amm_model = 'MODEL'; }],
  ['float control', w => { w.policy.controls.volatility_size_strength = 0.5; }],
  ['oversized exponent', w => { w.policy.controls.base_order_size = '1e-61'; }],
  ['nan', w => { w.policy.controls.max_distance_bps = 'NaN'; }],
  ['precision-sized overrun', w => { w.policy.controls.volatility_size_strength = '1.00000000000000000001'; }],
  ['concentration bounds', w => { w.policy.controls.concentration_upper_bps = '9'; }],
  ['inventory limits', w => { w.policy.controls.soft_inventory_limit_base = '4'; }],
  ['liquidity floor', w => { w.policy.controls.total_liquidity = '0.19999999999999999999'; }],
  ['changed override', w => { w.policy.controls.max_distance_bps = '101'; }],
  ['accounting units', w => { w.policy.hypothetical_accounting_unit.symbol = 'USDC'; }],
  ['undeclared risk', w => { w.policy.research_risk_fingerprint = '0'.repeat(64); }],
  ['unrequested advisory', w => { w.policy.advisory_snapshot_fingerprint = '0'.repeat(64); }],
  ['reference', w => { w.policy.simulated_reference_price = '2501'; }],
  ['declaration before observation', w => { w.policy.declared_at = observed_at.replace('.000001', ''); }],
  ['elevated authority', w => { w.policy.can_authorize_paper = true; }],
  ['unknown nested field', w => { w.policy.controls.size_multiplier = '10'; }],
  ['draft grants PAPER admission', w => { w.assessment.eligible_for_paper = true; }],
]) {
  test(`asset policy validator rejects resealed ${label}`, async () => {
    const { draft, request, selection } = await assetFixture();
    mutate(draft);
    draft.assessment.policy_fingerprint = await researchFingerprint(draft.policy);
    await assert.rejects(checkedAssetPolicyPreview(draft, request, selection), /Invalid or unsupported/);
  });
}

test('asset defaults require a cryptographic match and use exact bounded form inputs', async () => {
  const { draft, request, selection } = await assetFixture();
  await assert.rejects(checkedAssetPolicyPreview(draft, request, selection, Date.parse(observed_at)), /Invalid or unsupported/);
  draft.assessment.policy_fingerprint = 'f'.repeat(64);
  await assert.rejects(checkedAssetPolicyPreview(draft, request, selection), /Invalid or unsupported/);
  assert.equal(assetControlInput('volatility_size_strength', '1e-60'), '1e-60');
  assert.equal(assetControlInput('levels_per_side', '50'), 50);
  assert.throws(() => assetControlInput('levels_per_side', '2.0'), /whole number/);
  assert.throws(() => assetControlInput('volatility_size_strength', 'Infinity'), /exact decimal/);
  assert.equal(assetMinimumNotional('1e-12'), '1e-12');
  assert.throws(() => assetMinimumNotional('1e-13'), /12 decimal places/);
  assert.equal(assetReferenceIsValid('1e-13'), false);
});

for (const [reason, check, unavailable] of [
  ['ASSET_POLICY_FINGERPRINT_MISMATCH', 'asset_policy_fingerprint', false],
  ['ADVISORY_FINGERPRINT_MISMATCH', 'advisory_snapshot_fingerprint', false],
  ['ADVISORY_UNAVAILABLE', 'advisory_snapshot_fingerprint', true],
  ['ADVISORY_STALE', 'advisory_snapshot_fingerprint', true],
  ['ORDER_NOTIONAL_TOO_SMALL', 'minimum_order_notional', false],
]) {
  test(`PAPER preserves the typed ${reason} decision`, () => {
    const evidence = rejection(reason, check, unavailable);
    assert.equal(checkedPaperAdmission(evidence, proposal), evidence);
    evidence.status = 'ELIGIBLE';
    assert.throws(() => checkedPaperAdmission(evidence, proposal), /Invalid or unsupported/);
  });
}

test('PAPER validation retains canonical evidence and retires expired admission', () => {
  const accepted = checkedPaperAdmission(admission(), proposal);
  assert.equal(accepted.profile.metadata.identity.dex, 'xyz');
  assert.equal(accepted.profile.reference_source, 'USER_SUPPLIED_SYNTHETIC');
  assert.equal(paperAdmissionIsCurrent(accepted, Date.parse(evaluated_at)), true);
  assert.equal(paperAdmissionIsCurrent(accepted, Date.parse(valid_until)), false);
  const stale = checkedPaperAdmission(rejection('METADATA_STALE', 'freshness', true), proposal);
  assert.equal(paperAdmissionIsCurrent(stale), false);
  assert.equal(checkedPaperResult(result(), proposal, binding).result.metrics.fill_count, 4);
});

for (const [name, mutate] of [
  ['missing version', w => { delete w.profile_version; }],
  ['unsupported version', w => { w.profile_version = 'phase999'; }],
  ['mutated nested version', w => { w.profile.profile_version = 'phase999'; }],
  ['forged execution eligibility', w => { w.execution_eligible = true; }],
  ['noncanonical source market', w => { w.profile.metadata.source_coin = 'abc:GOLD'; }],
  ['foreign identity', w => { w.profile.metadata.identity.network = 'TESTNET'; }],
  ['stale eligible metadata', w => { w.profile.metadata.metadata_status = 'STALE'; }],
  ['expired eligible evidence', w => { w.valid_until = '2026-11-18T20:00:11Z'; }],
  ['expired eligible evidence within the same millisecond', w => { w.valid_until = '2026-11-18T20:00:12.000000Z'; }],
  ['forked profile digest', w => { w.binding.profile_fingerprint = '9'.repeat(64); }],
  ['forged discovery PAPER eligibility', w => { w.profile.discovery.paper_research_eligible = true; }],
  ['missing catalog binding', w => { delete w.binding.catalog_fingerprint; }],
  ['legacy evidence boundary', w => { delete w.profile.evidence_boundary; }],
  ['verified reference evidence', w => { w.profile.evidence_boundary.references = 'REDSTONE'; }],
  ['verified collateral evidence', w => { w.profile.evidence_boundary.exchange_economics = 'VERIFIED'; }],
  ['forged risk readiness', w => { w.profile.evidence_boundary.risk_readiness = 'RISK_READY'; }],
  ['additional authority marker', w => { w.profile.evidence_boundary.testnet_eligible = true; }],
  ['wrong synthetic assumption', w => { w.profile.simulated_reference_price = '2501'; }],
  ['unbounded precision', w => { w.profile.metadata.sz_decimals = 7; }],
]) {
  test(`PAPER validator fails closed on ${name}`, () => {
    const wire = admission();
    mutate(wire);
    assert.throws(() => checkedPaperAdmission(wire, proposal), /Invalid or unsupported/);
  });
}

test('PAPER result requires scoped execution and exact request identity and fingerprints', () => {
  const wrong = result();
  wrong.result.vault.mode = 'TESTNET';
  assert.throws(() => checkedPaperResult(wrong, proposal, binding), /Invalid or unsupported/);
  assert.throws(() => checkedPaperResult(result(), { ...proposal, frames: 12 }, binding), /Invalid or unsupported/);
  assert.throws(() => checkedPaperResult(result(), proposal, { ...binding, configuration_fingerprint: '9'.repeat(64) }),
    /Invalid or unsupported/);
  assert.throws(() => checkedPaperResult(result(), proposal, { ...binding, catalog_fingerprint: '9'.repeat(64) }),
    /Invalid or unsupported/);
  assert.throws(() => checkedPaperResult({ ...result(), started_at: valid_until }, proposal, binding), /Invalid or unsupported/);
  assert.throws(() => checkedPaperResult({ ...result(), started_at: observed_at }, proposal, binding), /Invalid or unsupported/);
});

test('PAPER client sends only the captured fingerprint binding to the research endpoint', async t => {
  const calls = [];
  const mock = t.mock.method(globalThis, 'fetch', (path, options) => {
    calls.push([path, options]);
    return new Response(JSON.stringify(path.endsWith('/eligibility') ? admission() : result()));
  });
  const accepted = await api.paperEligibility(proposal);
  assert.equal((await api.runGeneralizedPaper(proposal, accepted.binding)).execution_mode, 'PAPER');
  assert.deepEqual(calls.map(([p, o]) => [p, o.method, JSON.parse(o.body)]), [
    ['/api/v1/generalized-paper/eligibility', 'POST', proposal],
    ['/api/v1/generalized-paper/run', 'POST', { ...proposal, expected: binding }],
  ]);
  mock.mock.mockImplementation(() => new Response(JSON.stringify(rejection('MARKET_DELISTED', 'listing')), { status: 422 }));
  assert.equal((await api.paperEligibility(proposal)).reason, 'MARKET_DELISTED');
  mock.mock.mockImplementation(() => new Response(JSON.stringify(rejection('METADATA_STALE', 'freshness', true)), { status: 503 }));
  assert.equal((await api.runGeneralizedPaper(proposal, binding)).status, 'UNAVAILABLE');
  mock.mock.mockImplementation(() => new Response(JSON.stringify(rejection('MARKET_DELISTED', 'listing'))));
  await assert.rejects(api.paperEligibility(proposal), /disagrees with its HTTP status/);
});

const { boundedRiskInput, buildRiskSettings, checkedFinancialEvidence, financialEvidenceIsCurrent } = load('utils/marketRisk.js');

function publicFinancialEvidence() {
  const metadata = admission().profile.metadata;
  const selection = { metadata, metadata_fingerprint: binding.metadata_fingerprint,
    catalog_fingerprint: binding.catalog_fingerprint, max_age_seconds: 60 };
  const observation = { schema_version: 'phase183b-v1', source: 'HYPERLIQUID_INFO_META',
    metadata, metadata_fingerprint: binding.metadata_fingerprint, collateral_token_index: 1,
    collateral: { network: 'MAINNET', index: 1, symbol: 'USDC', token_id: '0x' + 'a'.repeat(32),
      namespace: 'hyperliquid.spot', observed_at, canonical: null },
    collateral_source: 'HYPERLIQUID_INFO_SPOT_META', collateral_status: 'SOURCE_OBSERVED',
    margin: { mode: 'NO_CROSS', reported_mode: 'noCross', only_isolated: true, table_id: 10,
      reported_max_leverage: 10, tier_source: 'DOCUMENTED_TABLE_ID', tiers: [{ lower_bound: '0', max_leverage: 10 }] },
    margin_status: 'SOURCE_OBSERVED', issues: [], price_quote_unit: null, settlement_unit: null,
    documented_units: null, account_mode: 'UNKNOWN', read_only: true, execution_eligible: false, authority: 'NONE' };
  return { selection, evidence: { schema_version: 'phase183e-v1', model_version: 'phase183c-v1',
    identity: structuredClone(identity), catalog_fingerprint: binding.catalog_fingerprint,
    metadata_fingerprint: binding.metadata_fingerprint, evaluated_at, valid_until, status: 'SOURCE_OBSERVED', observation,
    source_fingerprint: 'd'.repeat(64), source_constraint_reason: null, source_margin_modes: ['ISOLATED', 'NO_CROSS'],
    scope: 'LOCAL_PAPER_ONLY', read_only: true, execution_eligible: false, authority: 'NONE' } };
}

test('risk evidence binds selected network, current generation and exact public collateral', async () => {
  const { selection, evidence } = publicFinancialEvidence();
  const checked = checkedFinancialEvidence(evidence, selection);
  assert.equal(checked.observation.collateral.token_id, '0x' + 'a'.repeat(32));
  assert.equal(financialEvidenceIsCurrent(checked, Date.parse(evaluated_at)), true);
  assert.equal(financialEvidenceIsCurrent(checked, Date.parse(valid_until)), false);
  const originalFetch = global.fetch;
  global.fetch = async (url, options) => {
    const parsed = new URL(url, 'http://localhost');
    assert.equal(parsed.pathname, '/api/v1/market-universe/risk-evidence');
    assert.equal(parsed.searchParams.get('dex'), identity.dex);
    assert.equal(parsed.searchParams.get('catalog_fingerprint'), binding.catalog_fingerprint);
    assert.equal(options.cache, 'no-store');
    return new Response(JSON.stringify(evidence));
  };
  try { assert.deepEqual(await api.marketRiskEvidence(selection), checked); }
  finally { global.fetch = originalFetch; }
});

for (const [name, mutate] of [
  ['unknown envelope version', w => { w.schema_version = 'phase183e-v2'; }],
  ['unknown risk model version', w => { w.model_version = 'phase183c-v2'; }],
  ['different catalog', w => { w.catalog_fingerprint = 'e'.repeat(64); }],
  ['different market', w => { w.identity.dex = 'other'; }],
  ['different collateral network', w => { w.observation.collateral.network = 'TESTNET'; }],
  ['same-symbol token index substitution', w => { w.observation.collateral.index = 0; }],
  ['reserved PAPER unit impersonation', w => { w.observation.collateral.symbol = 'HYPOTHETICAL_QUOTE'; }],
  ['missing collateral', w => { w.observation.collateral = null; }],
  ['margin mode substitution', w => { w.source_margin_modes.push('CROSS'); }],
  ['stale source promoted to observed', w => { w.valid_until = '2026-11-18T20:00:11Z'; }],
  ['stale margin status promoted to observed', w => { w.observation.margin_status = 'STALE'; }],
  ['invalid Decimal', w => { w.observation.margin.tiers[0].lower_bound = 'NaN'; }],
  ['unbounded margin tiers', w => { w.observation.margin.tiers = Array(33).fill(w.observation.margin.tiers[0]); }],
  ['elevated nested authority', w => { w.observation.margin.risk_ready = true; }],
]) {
  test(`financial observation rejects ${name}`, () => {
    const { selection, evidence } = publicFinancialEvidence();
    mutate(evidence);
    assert.throws(() => checkedFinancialEvidence(evidence, selection), /Invalid or unsupported/);
  });
}

const shock = { name: 'decline', price_shock_bps: '-2500', collateral_loss_bps: '100',
  capital_reduction_bps: '0', funding_cost_bps: '12', fees_bps: '7' };
const settings = buildRiskSettings('HYPOTHETICAL', 'ISOLATED', '1000', '0.2', '0.1', '5', '5', '', [shock]);

test('hypothetical inputs keep exact Decimals and bound leverage, stress and capital', () => {
  assert.equal(settings.capital_paper_quote, '1000');
  assert.equal(settings.leverage, '5');
  assert.equal(settings.stresses[0].price_shock_bps, '-2500');
  assert.equal(boundedRiskInput('999999999.999999999999', '0', '1000000000'), '999999999.999999999999');
  assert.throws(() => boundedRiskInput('1000000000.000000000001', '0', '1000000000'));
  assert.throws(() => buildRiskSettings('HYPOTHETICAL', 'ISOLATED', '1000', '0.199999999999', '0.1', '5', '5', '', []),
    /reciprocal/);
  assert.throws(() => buildRiskSettings('HYPOTHETICAL', 'ISOLATED', '1000', '0.2', '0.1', '', '', '', [shock, shock]),
    /unique name/);
  assert.throws(() => buildRiskSettings('HYPOTHETICAL', 'ISOLATED', '1000', '0.2', '0.1', '', '', '',
    [{ ...shock, price_shock_bps: '-10000' }]), /bounds/);
});

function hypotheticalRiskResult() {
  const request = { ...proposal, frames: 2, research_risk: settings };
  const wire = result();
  wire.proposal = { ...wire.proposal, frames: 2, research_risk: structuredClone(settings) };
  wire.result.metrics.frame_count = 2;
  const digest = 'd'.repeat(64);
  const expected = { ...binding, research_risk_fingerprint: digest };
  const unit = { contract_version: 'phase183a-v1', network: 'MAINNET', kind: 'HYPOTHETICAL_QUOTE', symbol: 'HYPOTHETICAL_QUOTE',
    asset_namespace: '', asset_reference: null, provenance: 'RESEARCH_ASSUMPTION' };
  const noAuthority = { authority: 'NONE', execution_eligible: false };
  const operationalFlags = { exchange_margin_verified: false, shared_capital_eligible: false, cross_market_netting_eligible: false };
  wire.admission.binding = expected;
  wire.admission.risk_source_status = 'UNAVAILABLE';
  wire.admission.risk_model = {
    version: 'phase183c-v1', settings: structuredClone(settings), ...noAuthority,
    source: null, source_fingerprint: null, margin_unit: unit, formula: 'HYPOTHETICAL_LINEAR',
    declaration: { contract_version: 'phase183a-v1', ...noAuthority, ...operationalFlags, account_mode: 'UNKNOWN',
      margin_mode: 'ISOLATED', policy_evidence: 'HYPOTHETICAL', liquidation_price: null,
      initial_margin_fraction: '0.2', maintenance_margin_fraction: '0.1', modeled_max_leverage: '5',
      financial_units: { contract_version: 'phase183a-v1', metadata: structuredClone(wire.admission.profile.metadata),
        metadata_fingerprint: binding.metadata_fingerprint, paper_accounting_unit: unit, collateral_unit: null,
        price_quote_unit: null, settlement_unit: null, unit_evidence: 'DECLARED_UNVERIFIED',
        verified_collateral: false, verified_settlement: false, read_only: true, authority: 'NONE' } },
    readiness: { contract_version: 'phase183a-v1', identity: structuredClone(identity), metadata_fingerprint: binding.metadata_fingerprint,
      collateral_fingerprint: '2'.repeat(64), margin_policy_fingerprint: '3'.repeat(64), evaluated_at, status: 'BLOCKED',
      reason: 'COLLATERAL_NOT_ESTABLISHED', scope: 'SINGLE_MARKET_RESEARCH_ONLY', read_only: true, risk_ready: false,
      leverage_eligible: false, ...noAuthority, ...operationalFlags },
  };
  const requirement = { initial: '10', maintenance: '5', tier_lower_bound: null,
    source_max_leverage: null, margin_leverage: null, leverage_supported: true };
  const margin = { unit, capital: '1000', current: requirement, projected_long: requirement, projected_short: requirement,
    projected_initial: '10', projected_maintenance: '5', initial_headroom: '990', maintenance_headroom: '995',
    projected_headroom: '990', projected_utilization: '0.01' };
  const { exposureDecimals } = load('types/marketRisk.js');
  wire.research_risk = { version: 'phase183d-v1', ...noAuthority, model_fingerprint: digest,
    capital_treatment: 'SEPARATE_RESEARCH_BUDGET', final_snapshot_status: 'MODELED',
    frames: ['NORMAL', 'HALT'].map((state, index) => ({ sequence: index + 1, state, candidate_quotes: 2,
      authorized_quotes: index ? 0 : 2, margin_retired_quotes: !!index, projected_headroom: '990', decision_reasons: [] })),
    final_snapshot: { ...noAuthority, valuation_time: '2026-11-18T20:00:14Z', configuration_fingerprint: digest, margin,
      exposure: { ...Object.fromEntries(exposureDecimals.map(key => [key, '0'])),
        base_instrument: structuredClone(identity), quote_unit: unit, signed_base: '1.25' },
      stresses: [{ assumptions: structuredClone(shock), mark_paper_quote_per_base: '100', adverse_pnl_paper_quote: '-30',
        costs_paper_quote: '3', margin, headroom_deterioration: '25', tier_changed: false, feasible: true }] } };
  return { wire, request, expected: structuredClone(expected) };
}

test('risk result verifies configuration, modeled units, terminal position and Firewall decisions', () => {
  const { wire, request, expected } = hypotheticalRiskResult();
  const checked = checkedPaperResult(wire, request, expected);
  assert.equal(checked.research_risk.frames[1].state, 'HALT');
  assert.equal(checked.research_risk.final_snapshot.stresses[0].headroom_deterioration, '25');
});

for (const [name, mutate] of [
  ['model evidence omitted', w => { delete w.admission.risk_model; }],
  ['model made operational', w => { w.admission.risk_model.readiness.risk_ready = true; }],
  ['changed capital', w => { w.admission.risk_model.settings.capital_paper_quote = '900'; }],
  ['wrong model binding', w => { w.research_risk.model_fingerprint = 'f'.repeat(64); }],
  ['wrong final position', w => { w.research_risk.final_snapshot.exposure.signed_base = '-1.25'; }],
  ['wrong exposure namespace', w => { w.research_risk.final_snapshot.exposure.base_instrument.dex = 'other'; }],
  ['wrong margin unit', w => { w.research_risk.final_snapshot.margin.unit = { symbol: 'USDC' }; }],
  ['malformed stress', w => { w.research_risk.final_snapshot.stresses[0].adverse_pnl_paper_quote = Infinity; }],
  ['changed stress', w => { w.research_risk.final_snapshot.stresses[0].assumptions.collateral_loss_bps = '500'; }],
  ['unbounded frames', w => { w.research_risk.frames = Array(121).fill(w.research_risk.frames[0]); }],
  ['HALT with authorized quotes', w => { w.research_risk.frames[1].authorized_quotes = 1; }],
]) {
  test(`risk result rejects ${name}`, () => {
    const { wire, request, expected } = hypotheticalRiskResult();
    mutate(wire);
    assert.throws(() => checkedPaperResult(wire, request, expected), /Invalid or unsupported/);
  });
}
