const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { currentSourcePrices } = require(path.join(process.env.TERMINAL_TEST_BUILD, 'utils/freshness.js'));
const { validateTerminal } = require(path.join(process.env.TERMINAL_TEST_BUILD, 'utils/validateTerminal.js'));
const { mergeHistory } = require(path.join(process.env.TERMINAL_TEST_BUILD, 'utils/terminalHistory.js'));
const valid = require('./fixtures/terminal-valid.json');

function terminal() {
  const t = structuredClone(valid);
  t.reference_consensus.updated_at = t.emitted_at;
  t.reference_consensus.eligible_providers = ['REDSTONE', 'KRAKEN'];
  for (const provider of ['REDSTONE', 'KRAKEN']) {
    Object.assign(t.references.evidence[provider], { stale: false, healthy: true });
  }
  t.perp_context.stale = false;
  return t;
}
test('fresh terminal transport cannot lend freshness to stale source prices', () => {
  const t = terminal();
  t.perp_context.stale = true;
  t.references.evidence.KRAKEN.stale = true;
  t.references.evidence.KRAKEN.healthy = false;
  // Last provider status and last decision deliberately remain healthy/VERIFIED.
  t.references.evidence.KRAKEN.status = 'HEALTHY';
  t.reference_consensus.confidence_state = 'VERIFIED';
  assert.equal(validateTerminal(t), t);
  assert.deepEqual(currentSourcePrices(t), {
    mark_price: null, oracle_price: null, strategy_reference_price: null, consensus_price: null,
  });
  assert.equal(t.reference_consensus.confidence_state, 'VERIFIED');
});
test('fresh supported degraded consensus remains available, tertiary staleness does not recalculate quorum', () => {
  const t = terminal();
  t.reference_consensus.confidence_state = 'DEGRADED';
  t.references.evidence.COINGECKO.stale = true;
  const before = structuredClone(t);
  assert.equal(currentSourcePrices(t).consensus_price, t.reference_consensus.consensus_price);
  assert.equal(currentSourcePrices(t).mark_price, t.perp_context.mark_price);
  assert.deepEqual(t, before);
});
test('absent, unavailable or future retained consensus never supplies a current price', () => {
  for (const change of [
    t => { t.references = null; },
    t => { t.reference_consensus = null; },
    t => { t.reference_consensus.eligible_providers = []; },
    t => { delete t.references.evidence.KRAKEN; },
    t => { t.references.evidence.KRAKEN.healthy = false; },
    t => { t.references.evidence.KRAKEN.price = null; },
    t => { t.reference_consensus.updated_at = new Date(Date.parse(t.emitted_at) + 40000).toISOString(); },
  ]) {
    const t = terminal(); change(t);
    assert.equal(currentSourcePrices(t).consensus_price, null);
  }
  assert.deepEqual(currentSourcePrices(null), {
    mark_price: null, oracle_price: null, strategy_reference_price: null, consensus_price: null,
  });
});
test('stale live point stays suppressed through a delayed history watermark merge', () => {
  const t = terminal();
  t.perp_context.stale = true;
  t.references.evidence.KRAKEN.stale = true;
  const live = { sequence: 113, timestamp: t.emitted_at, ...currentSourcePrices(t) };
  const state = { session: t.session_id, range: 'session', points: [live] };
  const history = { session_id: t.session_id, range: 'session', points: [
    { sequence: 110, timestamp: new Date(Date.parse(t.emitted_at) - 3000).toISOString(), mark_price: '3000', consensus_price: '3000' },
  ] };
  const merged = mergeHistory(state, history, 1000);
  assert.equal(merged.points.at(-1), live);
  assert.equal(merged.points.at(-1).mark_price, null);
  assert.equal(merged.points.at(-1).consensus_price, null);
});
