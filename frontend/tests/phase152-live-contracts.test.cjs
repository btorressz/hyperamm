const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const ts = require('typescript');
const { api } = require(path.join(process.env.TERMINAL_TEST_BUILD, 'api/client.js'));

for (const market of ['BTC', 'ETH', 'SOL']) {
  test(`phase152 ${market} observation APIs send GET and preserve wire evidence`, async () => {
    const original = global.fetch;
    const calls = [];
    const evidence = {market, price: '60000.00001', source_timestamp: null, authority: 'NONE'};
    global.fetch = async (url, init) => {
      calls.push({url, init});
      return {ok: true, status: 200, json: async () => evidence};
    };
    try {
      const controller = new AbortController();
      assert.equal(await api.liveStreamStatus(market, controller.signal), evidence);
      assert.equal(await api.liveStreamSnapshot(market, controller.signal), evidence);
      assert.equal(await api.liveMarketHistory(market, 7, controller.signal), evidence);
      assert.equal(await api.liveProviderHealth(market, controller.signal), evidence);
      assert.deepEqual(calls.map(c => c.url), [
        `/api/v1/live-markets/${market}/stream-status`, `/api/v1/live-markets/${market}/stream-snapshot`,
        `/api/v1/live-markets/${market}/history?limit=7`, `/api/v1/live-markets/${market}/references`]);
      assert.ok(calls.every(c => !c.init.method && c.init.signal === controller.signal && !c.init.body));
      assert.equal(evidence.price, '60000.00001');
      assert.equal(evidence.source_timestamp, null);
    } finally {global.fetch = original;}
  });
}

test('phase152 TypeScript contracts keep financial strings, null times and separate publication identities', () => {
  const filename = path.resolve(__dirname, 'phase152-contract-probe.ts');
  const source = `
    import type { LiveMarketStreamEnvelope, LiveMarketHistory, LiveProviderHealth, LiveStreamSnapshot } from '../src/types';
    type Equal<A, B> = (<T>() => T extends A ? 1 : 2) extends (<T>() => T extends B ? 1 : 2) ? true : false;
    type Assert<T extends true> = T;
    type Decimal = Assert<Equal<NonNullable<LiveStreamSnapshot['order_book']>['midpoint'], string>>;
    type ContextTime = Assert<Equal<NonNullable<LiveStreamSnapshot['perp_context']>['source_timestamp'], null>>;
    type UnknownEvent = Assert<Equal<LiveStreamSnapshot['status']['perp_event_time'], 'UNKNOWN'>>;
    type Identity = Assert<Equal<LiveMarketStreamEnvelope['observer_instance_id'], string>>;
    type Sequence = Assert<Equal<LiveMarketStreamEnvelope['sequence'], number>>;
    type Coverage = Assert<Equal<LiveMarketHistory['coverage_start'], string | null>>;
    type Authority = Assert<Equal<LiveProviderHealth['authority'], 'NONE'>>;
    type Consensus = Assert<Equal<LiveProviderHealth['consensus_price'], null>>;
    type HistoryPrice = Assert<Equal<LiveMarketHistory['points'][number]['midpoint'], string | null>>;
    type ProviderPrice = Assert<Equal<LiveProviderHealth['providers'][number]['price'], string | null>>;
  `;
  const options = {strict: true, noEmit: true, skipLibCheck: true, target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ESNext, moduleResolution: ts.ModuleResolutionKind.Bundler};
  const host = ts.createCompilerHost(options), read = host.readFile.bind(host);
  host.readFile = file => file === filename ? source : read(file);
  const program = ts.createProgram([filename], options, host);
  const errors = ts.getPreEmitDiagnostics(program).filter(d => d.category === ts.DiagnosticCategory.Error);
  assert.deepEqual(errors.map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
});
