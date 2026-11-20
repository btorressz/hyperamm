const assert = require('node:assert/strict');
const test = require('node:test');
const path = require('node:path');
const load = name => require(path.join(process.env.TERMINAL_TEST_BUILD, name));
const { api } = load('api/client.js');
const { checkedMarketUniverse, marketUniverseKey, marketCatalogDeadline, marketResearchAvailability, matchesMarketResearchHandoff } = load('utils/marketUniverse.js');
const { researchMarketIds } = load('utils/researchMarkets.js');

const contract_version = 'phase180b-v2';
const observed_at = '2026-11-18T20:00:00.000001Z';
const evaluated_at = '2026-11-18T20:01:00.000001Z';
const readOnly = { read_only: true, authority: 'NONE' };
const discoveryOnly = { ...readOnly, paper_research_eligible: false, execution_eligible: false };
const digest = 'a'.repeat(64);
const check = { contract_version, status: 'REFRESHED', observed_at, error: null };

function available(network = 'MAINNET') {
  const records = ['', 'abc', 'xyz'].map(dex => ({
    contract_version,
    identity: { contract_version, venue: 'HYPERLIQUID', network, dex,
      instrument_type: dex ? 'HIP3_PERP' : 'CORE_PERP', instrument_name: 'BTC' },
    source_coin: dex ? `${dex}:BTC` : 'BTC', universe_index: 0, sz_decimals: 5, listed: dex !== 'abc',
    metadata_status: 'EXCHANGE_VERIFIED',
    metadata_source: dex ? 'OFFICIAL_SDK_HIP3_META' : 'OFFICIAL_SDK_CORE_META', observed_at,
  }));
  return {
    contract_version, schema_version: 'phase181-v1', ...discoveryOnly, network, availability: 'AVAILABLE',
    catalog: { contract_version, ...readOnly, records }, catalog_fingerprint: digest,
    eligibility: records.map(({ identity, listed }) => ({
      contract_version, ...discoveryOnly, identity: structuredClone(identity), metadata_fingerprint: digest,
      evaluated_at, reason: listed ? 'DISCOVERABLE' : 'NOT_LISTED', discovery_eligible: listed,
    })),
    evaluated_at, max_age_seconds: 60, inventory: { ...check }, namespaces: records.map(({ identity }) => ({
      ...check, dex: identity.dex,
    })),
    limitations: ['METADATA_ONLY', 'NO_PAPER_RESEARCH', 'NO_EXECUTION'], error: null,
  };
}

function unavailable(error) {
  return { ...available(), availability: 'UNAVAILABLE', catalog: null, catalog_fingerprint: null,
    eligibility: [], namespaces: [], inventory: { ...check, status: 'FAILED', observed_at: null, error } };
}

test('Phase 18.1 validates a canonical catalog while keeping native selectors scoped', () => {
  const result = checkedMarketUniverse(available('TESTNET'));
  assert.deepEqual(result.catalog.records.map(row => marketUniverseKey(row.identity)), [
    'HYPERLIQUID:TESTNET:CORE_PERP::BTC', 'HYPERLIQUID:TESTNET:HIP3_PERP:abc:BTC', 'HYPERLIQUID:TESTNET:HIP3_PERP:xyz:BTC',
  ]);
  assert.equal(result.eligibility[1].reason, 'NOT_LISTED');
  assert.deepEqual(researchMarketIds, ['BTC', 'ETH', 'SOL']);
  assert.notEqual(marketUniverseKey(result.catalog.records[0].identity),
    marketUniverseKey(available().catalog.records[0].identity));
});

for (const [name, mutate] of [
  ['unknown schema', w => { w.schema_version = 'phase999'; }],
  ['old identity version', w => { w.catalog.records[0].identity.contract_version = 'phase180a-v1'; }],
  ['wrong network', w => { w.catalog.records[0].identity.network = 'TESTNET'; }],
  ['unsupported market class', w => { w.catalog.records[0].identity.instrument_type = 'SPOT'; }],
  ['Core DEX collision', w => { w.catalog.records[0].identity.dex = 'abc'; }],
  ['ambiguous namespace', w => { w.catalog.records[1].identity.dex = 'abc:xyz'; }],
  ['trailing newline in identity', w => { w.catalog.records[1].identity.instrument_name += '\n'; }],
  ['namespace/source mismatch', w => { w.catalog.records[1].source_coin = 'z:BTC'; }],
  ['wrong metadata provenance', w => { w.catalog.records[1].metadata_source = 'OFFICIAL_SDK_CORE_META'; }],
  ['nonexistent calendar day', w => { w.evaluated_at = '2026-11-31T20:00:00Z'; }],
  ['invalid fingerprint', w => { w.catalog_fingerprint = 'a'.repeat(63) + '\n'; }],
  ['forged PAPER permission', w => { w.eligibility[0].paper_research_eligible = true; }],
  ['forged execution permission', w => { w.execution_eligible = true; }],
  ['foreign eligibility row', w => { w.eligibility.reverse(); }],
  ['unordered records', w => { w.catalog.records.reverse(); }],
  ['duplicate local index', w => {
    const row = structuredClone(w.catalog.records[2]);
    row.identity.instrument_name = 'DOGE';
    row.source_coin = 'xyz:DOGE';
    w.catalog.records.push(row);
    w.eligibility.push({ ...w.eligibility[2], identity: row.identity });
  }],
  ['out-of-range index', w => { w.catalog.records[0].universe_index = 110000; }],
  ['invalid precision', w => { w.catalog.records[0].sz_decimals = 2.5; }],
  ['duplicate namespace', w => { w.namespaces.push(w.namespaces[2]); }],
  ['inconsistent namespace clock', w => { w.namespaces[0].observed_at = w.evaluated_at; }],
  ['expired microsecond timing', w => {
    w.evaluated_at = '2026-11-18T20:01:00.000002Z';
    w.eligibility.forEach(row => { row.evaluated_at = w.evaluated_at; });
  }],
]) {
  test(`Phase 18.1 rejects ${name}`, () => {
    const wire = available();
    mutate(wire);
    assert.throws(() => checkedMarketUniverse(wire), /Invalid or unsupported/);
  });
}

test('Phase 18.1 distinguishes partial, unavailable, disabled and retained stale evidence', () => {
  const partial = available();
  partial.availability = 'PARTIAL';
  partial.namespaces[1] = { ...partial.namespaces[1], status: 'FAILED', observed_at: null, error: 'MISSING_METADATA' };
  partial.catalog.records.forEach(row => { row.metadata_status = 'STALE'; });
  partial.eligibility.forEach(row => {
    if (row.discovery_eligible) row.reason = 'STALE_METADATA';
    row.discovery_eligible = false;
  });
  assert.equal(checkedMarketUniverse(partial).eligibility[0].reason, 'STALE_METADATA');
  partial.eligibility[0].discovery_eligible = true;
  assert.throws(() => checkedMarketUniverse(partial), /Invalid or unsupported/);
  assert.equal(checkedMarketUniverse(unavailable('INVALID_DATA')).catalog, null);
  assert.equal(checkedMarketUniverse({
    ...unavailable('DISABLED'), availability: 'DISABLED', inventory: null, error: 'DISABLED',
  }).availability, 'DISABLED');
});

test('Phase 18.1 API client performs only GET and validates structured error statuses', async t => {
  const signal = new AbortController().signal;
  const calls = [];
  const mock = t.mock.method(globalThis, 'fetch', (url, options) => {
    calls.push([url, options]);
    return new Response(JSON.stringify(available()));
  });
  assert.equal((await api.marketUniverse(signal)).availability, 'AVAILABLE');
  assert.deepEqual(calls, [['/api/v1/market-universe', { method: 'GET', signal, cache: 'no-store' }]]);
  for (const [code, status] of [['RATE_LIMITED', 429], ['TIMEOUT', 504], ['INVALID_DATA', 503]]) {
    mock.mock.mockImplementation(() => new Response(JSON.stringify(unavailable(code)), { status }));
    assert.equal((await api.marketUniverse()).inventory.error, code);
  }
  mock.mock.mockImplementation(() => new Response(JSON.stringify(unavailable('TIMEOUT')), { status: 200 }));
  await assert.rejects(api.marketUniverse(), /disagrees with its HTTP status/);
  mock.mock.mockImplementation(() => new Response('private proxy data', { status: 502 }));
  await assert.rejects(api.marketUniverse(), error => /unexpected status/.test(error.message) &&
    !error.message.includes('private proxy data'));
});

test('Phase 18.1 API client applies its byte limit to declared and chunked responses', async t => {
  const mock = t.mock.method(globalThis, 'fetch', () => new Response('{}', {
    headers: { 'Content-Length': '5000001' },
  }));
  await assert.rejects(api.marketUniverse(), /evidence budget/);
  mock.mock.mockImplementation(() => new Response(new ReadableStream({
    start(controller) {
      controller.enqueue(new Uint8Array(5_000_000));
      controller.enqueue(new Uint8Array(1));
      controller.close();
    },
  })));
  await assert.rejects(api.marketUniverse(), /evidence budget/);
});

test('Explorer handoff keeps same-symbol Core and HIP-3 records and networks distinct', () => {
  const catalog = available();
  catalog.eligibility[2].metadata_fingerprint = 'b'.repeat(64);
  const target = catalog.eligibility[2];
  const handoff = {
    key: marketUniverseKey(target.identity),
    catalogFingerprint: catalog.catalog_fingerprint,
    metadataFingerprint: target.metadata_fingerprint,
  };
  const now = Date.parse(catalog.evaluated_at) - 100;
  assert.equal(matchesMarketResearchHandoff(catalog, handoff, now), true);
  assert.equal(matchesMarketResearchHandoff(catalog, { ...handoff, key: marketUniverseKey(catalog.eligibility[0].identity) }, now), false);
  assert.equal(matchesMarketResearchHandoff(available('TESTNET'), handoff, now), false);
  assert.equal(matchesMarketResearchHandoff({ ...catalog, catalog_fingerprint: 'c'.repeat(64) }, handoff, now), false);
  assert.equal(matchesMarketResearchHandoff(catalog, handoff, marketCatalogDeadline(catalog)), false);
  assert.equal(marketResearchAvailability(catalog, -1, true), 'unsupported');
  assert.equal(marketResearchAvailability(catalog, 1, true), 'unsupported');
  assert.equal(marketResearchAvailability(catalog, 2, false), 'unavailable');
});
