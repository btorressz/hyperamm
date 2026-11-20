const assert = require('node:assert/strict');
const path = require('node:path');
const test = require('node:test');
const load = name => require(path.join(process.env.TERMINAL_TEST_BUILD, name));
const { api } = load('api/client.js');
const { marketUniverseKey } = load('utils/marketUniverse.js');
const { checkedMarketSummaries, observedNumber } = load('utils/marketSummaries.js');
const { researchFingerprint } = load('utils/researchFingerprint.js');

const readOnly = { read_only: true, execution_eligible: false, authority: 'NONE' };
const identity = { contract_version: 'phase180b-v2', venue: 'HYPERLIQUID', network: 'MAINNET',
  instrument_type: 'HIP3_PERP', dex: 'xyz', instrument_name: 'GOLD' };
const scope = { network: 'MAINNET', catalogFingerprint: 'a'.repeat(64),
  markets: [{ key: marketUniverseKey(identity), metadataFingerprint: 'b'.repeat(64), universeIndex: 3, listed: true }] };
const observed_at = '2026-11-20T12:00:10.123456Z';
const evaluated_at = '2026-11-20T12:00:11.000001Z';
const valid_until = '2026-11-20T12:00:40.123456Z';

async function available() {
  const row = { ...readOnly, identity: structuredClone(identity), universe_index: 3,
    metadata_fingerprint: scope.markets[0].metadataFingerprint, status: 'CURRENT', error: null,
    mark_price: '2354.3201', oracle_price: null, previous_day_price: '2000',
    mark_change_vs_previous_day_percent: '17.71600500', funding_rate: '-0.000025',
    funding_interval_seconds: 3600, day_notional_volume: '1000507', open_interest_base: '0',
    price_unit: 'PROVIDER_QUOTE_PER_BASE', notional_unit: 'PROVIDER_NOTIONAL_QUOTE',
    open_interest_unit: 'BASE', funding_unit: 'RATE_PER_INTERVAL', observed_at, valid_until,
    provider_event_at: null, observation_clock: 'LOCAL_RECEIPT', limitations: ['oraclePx:MISSING'],
    source: 'HYPERLIQUID_INFO_META_AND_ASSET_CTXS' };
  const capture = { ...row, observation_fingerprint: await researchFingerprint({
    catalog_fingerprint: scope.catalogFingerprint, ...row,
  }) };
  return { ...readOnly, schema_version: 'phase186h-v1', network: scope.network,
    catalog_fingerprint: scope.catalogFingerprint, evaluated_at,
    valid_until: '2026-11-20T12:00:55.100100Z', results: [capture] };
}

test('read-only exact mark, signed funding and zero interest survive a missing oracle', async () => {
  const wire = await available();
  assert.deepEqual(await checkedMarketSummaries(wire, scope), wire);
  const row = wire.results[0];
  assert.equal(row.oracle_price, null);
  assert.equal(observedNumber(row.funding_rate, '%'), '-0.0025%');
  assert.equal(observedNumber(row.open_interest_base), '0');
  assert.equal(observedNumber(row.oracle_price), 'Unavailable');
  assert.equal(observedNumber('0.0000000000000000001'), '0.0000000000000000001');
});

for (const [name, change] of [
  ['authority', wire => { wire.execution_eligible = true; }],
  ['row authority', (_, row) => { row.authority = 'ORDER'; }],
  ['schema', wire => { wire.schema_version = 'future'; }],
  ['network', wire => { wire.network = 'TESTNET'; }],
  ['namespace', (_, row) => { row.identity.dex = 'abc'; }],
  ['canonical class', (_, row) => { row.identity.instrument_type = 'CORE_PERP'; }],
  ['index', (_, row) => { row.universe_index = 4; }],
  ['catalog generation', wire => { wire.catalog_fingerprint = 'c'.repeat(64); }],
  ['metadata digest', (_, row) => { row.metadata_fingerprint = 'c'.repeat(64); }],
  ['observation digest', (_, row) => { row.observation_fingerprint = 'c'.repeat(64); }],
  ['duplicated rows', wire => { wire.results.push(structuredClone(wire.results[0])); }],
  ['nonexact mark', (_, row) => { row.mark_price = 2354.32; }],
  ['zero mark', (_, row) => { row.mark_price = '0'; }],
  ['missing comparison input', (_, row) => { row.previous_day_price = null; }],
  ['nonfinite interest', (_, row) => { row.open_interest_base = 'Infinity'; }],
  ['negative volume', (_, row) => { row.day_notional_volume = '-0.001'; }],
  ['precision beyond funding cap', (_, row) => { row.funding_rate = '0.005000000000000000001'; }],
  ['funding interval', (_, row) => { row.funding_interval_seconds = 28800; }],
  ['units', (_, row) => { row.price_unit = 'USDC'; }],
  ['wrong operation', (_, row) => { row.source = 'predictedFundings'; }],
  ['server expiry', (_, row) => { row.valid_until = evaluated_at; }],
  ['freshness budget', (_, row) => { row.valid_until = '2026-11-20T12:00:40.123457Z'; }],
  ['fake event clock', (_, row) => { row.provider_event_at = observed_at; }],
  ['values on stale capture', (_, row) => { row.status = 'STALE'; }],
]) {
  test(`rejects incompatible summary ${name}`, async () => {
    const wire = await available();
    change(wire, wire.results[0]);
    await assert.rejects(checkedMarketSummaries(wire, scope));
  });
}

test('summary API requests only the scoped canonical selectors and consumes cancellation', async () => {
  const original = global.fetch;
  const controller = new AbortController();
  try {
    global.fetch = async (url, options) => {
      assert.match(url, /\/market-universe\/market-summaries$/);
      assert.equal(options.method, 'POST');
      assert.equal(options.cache, 'no-store');
      assert.equal(options.signal, controller.signal);
      assert.deepEqual(JSON.parse(options.body), {
        network: scope.network, catalog_fingerprint: scope.catalogFingerprint,
        market_keys: scope.markets.map(market => market.key), refresh: true,
      });
      return Response.json(await available());
    };
    const result = await api.marketSummaries(scope, true, controller.signal);
    assert.equal(result.results[0].mark_price, '2354.3201');
    global.fetch = async () => new Response('', { status: 409 });
    await assert.rejects(api.marketSummaries(scope, false), /Catalog changed/);
  } finally {
    global.fetch = original;
  }
});
