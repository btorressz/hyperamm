// Backend-generated retained-evidence and provider states cross the real TS gate.
const {test}=require('node:test'),assert=require('node:assert/strict');
const {load}=require('./phase153-test-helpers.cjs');
const fixtures=require('./phase155b-fixtures.json');
const {checkedLiveEnvelope,checkedLiveProviders,checkedLiveHistory,liveFreshness}=load('utils/liveMarketEvidence.js');
const {liveChartSegments}=load('utils/liveMarketHistory.js');
const {useLiveMarketStore:store}=load('stores/liveMarkets.js');
for(const market of ['BTC','ETH','SOL']){
  test(`${market}: backend retained valid evidence crosses TS validation as DEGRADED`,()=>{
    const f=fixtures[market],now=Date.parse(f.active.emitted_at);
    const active=checkedLiveEnvelope(f.active,market,now),bad=checkedLiveEnvelope(f.degraded,market,now);
    assert.equal(active.observation_status,'AVAILABLE');assert.equal(bad.observation_status,'DEGRADED');
    assert.deepEqual(bad.payload.order_book,active.payload.order_book);
    assert.deepEqual(bad.payload.perp_context,active.payload.perp_context);
    const health=checkedLiveProviders(f.health,market,now);
    assert.equal(health.providers[0].status,'DEGRADED');assert.equal(health.providers[0].price,active.payload.order_book.midpoint);
    assert.equal(health.independent_usable_external_sources,0);assert.equal(health.consensus_price,null);
    assert.ok(health.providers.slice(1,3).every(p=>!p.event_time_verified&&p.source_timestamp===null));
  });
  test(`${market}: newer degraded publication cannot renew original source age`,()=>{
    const f=fixtures[market],snapshot=f.degraded.payload;
    const age=liveFreshness({snapshot,receivedAt:0,transitSeconds:0},11000,true);
    assert.equal(age.book,false);assert.ok(age.ages.l2>=11);
  });
  test(`${market}: actual history validates and explicit gap never interpolates`,()=>{
    const f=fixtures[market],history=checkedLiveHistory(f.history,market,f.active.observer_instance_id,100,Date.parse(f.active.emitted_at));
    const withGap={...history,gap_count:1};
    assert.ok(liveChartSegments(withGap,'midpoint',30).every(s=>s.length<=1));
    assert.equal(history.continuous_history_verified,false);
  });
}
test('real backend degraded frame cannot cross the selected market boundary',()=>{
  store.getState().selectMarket('ETH');const epoch=store.getState().selectionEpoch;
  const eth=fixtures.ETH.active;store.getState().acceptSnapshot(eth.payload,epoch,0,0);
  assert.equal(store.getState().acceptFrame(fixtures.BTC.degraded,epoch,1,0),false);
  assert.equal(store.getState().evidence.snapshot.market,'ETH');
});
test('cached healthy provider row immediately follows degraded stream health before next HTTP poll',()=>{
  const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
  const {LiveProviderStatus}=load('components/markets/LiveProviderStatus.js');
  const health=structuredClone(fixtures.BTC.health);
  health.providers[0].status='HEALTHY';health.providers[0].error=null;
  const props={evidence:{health,receivedAt:0,transitSeconds:0},now:0,current:true,bookCurrent:true,perpCurrent:true,bookBudget:10,perpBudget:30};
  const row=sourceDegraded=>renderToStaticMarkup(React.createElement(LiveProviderStatus,{...props,sourceDegraded})).split('<tbody>')[1].split('</tr>')[0];
  assert.match(row(false),/HEALTHY/);
  assert.doesNotMatch(row(true),/HEALTHY/);assert.match(row(true),/DEGRADED/);
  assert.match(row(true),/Native source degraded/);
  assert.equal(health.providers[0].status,'HEALTHY');
});
