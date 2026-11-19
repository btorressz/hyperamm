const assert = require('node:assert/strict');
const test = require('node:test');
const path = require('node:path');
const load = name => require(path.join(process.env.TERMINAL_TEST_BUILD, name));
const { api } = load('api/client.js');
const { paperEvidenceBoundary } = load('types/generalizedPaper.js');
const { checkedPaperAdmission, checkedPaperResult, paperAdmissionIsCurrent } = load('utils/generalizedPaper.js');
const { marketUniverseKey } = load('utils/marketUniverse.js');

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
