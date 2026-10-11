const {test}=require('node:test'),assert=require('node:assert/strict');
const {load,fixture}=require('./phase153-test-helpers.cjs');
const e=load('utils/liveMarketEvidence.js'),f=load('utils/format.js');
for(const m of ['BTC','ETH','SOL'])test(`${m} validates actual backend-shaped stream, history and provider evidence`,()=>{
  const s=fixture(m);assert.equal(e.checkedLiveSnapshot(s,m).market,m);
  const frame=fixture(m,'envelope');assert.equal(e.checkedLiveEnvelope(frame,m).market,m);
  assert.equal(e.checkedLiveHistory(fixture(m,'history'),m,s.status.observer_instance_id,1000).market,m);
  assert.equal(e.checkedLiveProviders(fixture(m,'providers'),m).authority,'NONE');
  assert.equal(s.perp_context.source_timestamp,null);
});
for(const [name,change] of [
  ['wrong market',s=>s.market='ETH'],['payload market',s=>s.order_book.market='ETH'],['generation',s=>s.status.connection_generation=true],
  ['status',s=>s.observation_status='LIVE'],['NaN',s=>s.order_book.midpoint='NaN'],['Infinity',s=>s.perp_context.funding_rate='Infinity'],
  ['binary financial',s=>s.order_book.bids[0].price=60000],['negative size',s=>s.order_book.bids[0].size='-1'],
  ['crossed book',s=>s.order_book.best_ask=s.order_book.best_bid],['bad date',s=>s.status.evaluated_at='2026-02-30T00:00:00Z'],
  ['future',s=>s.status.evaluated_at=new Date(Date.now()+5000).toISOString()],['perp event time',s=>s.perp_context.source_timestamp=s.perp_context.observed_at],
  ['fresh missing book',s=>s.order_book=null],['metadata',s=>s.metadata.listed=false],['malformed age',s=>s.status.l2_age_seconds='0'],
  ['missing budget',s=>delete s.status.l2_stale_after_seconds],['bad levels',s=>s.order_book.bids=null],['missing source',s=>delete s.order_book.source],
])test(`snapshot rejects ${name}`,()=>{const s=fixture();change(s);assert.throws(()=>e.checkedLiveSnapshot(s,'BTC'));});
for(const [name,change] of [['contract',v=>v.contract_version='next'],['observer mismatch',v=>v.observer_instance_id='old'],['generation mismatch',v=>v.connection_generation++],['zero sequence',v=>v.sequence=0],['bad emission',v=>v.emitted_at='today'],['future emission',v=>v.emitted_at=new Date(Date.now()+5000).toISOString()]])test(`envelope rejects ${name}`,()=>{const v=fixture('BTC','envelope');change(v);assert.throws(()=>e.checkedLiveEnvelope(v,'BTC'));});
test('HTTP 200 disabled and open WS bootstrapping never imply available streaming',()=>{
  const disabled=fixture('BTC','disabled');assert.equal(e.checkedLiveSnapshot(disabled,'BTC').observation_status,'DISABLED');
  assert.equal(e.liveFreshness({snapshot:disabled,receivedAt:0,transitSeconds:0},1,true).book,false);
  const s=fixture('BTC','bootstrap');assert.equal(s.status.connection_state,'BOOTSTRAPPING');
  assert.equal(s.order_book.source,'OFFICIAL_SDK_REST');assert.equal(s.observation_status,'PARTIAL');
  assert.equal(e.liveFreshness({snapshot:s,receivedAt:0,transitSeconds:0},1,true).book,true);
});
for(const [name,elapsed,book,perp] of [['fresh',0,true,true],['book stale',11000,false,true],['both stale',31000,false,false]])test(`monotonic projection ${name}`,()=>{
  const s=fixture(),original=structuredClone(s);const view=e.liveFreshness({snapshot:s,receivedAt:100,transitSeconds:0},100+elapsed,true);
  assert.equal(view.book,book);assert.equal(view.perp,perp);assert.deepEqual(s,original);
});
test('context stale independently of fresh L2; disconnect and unreliable monotonic clock retire claims',()=>{
  const s=fixture();s.status.perp_freshness='STALE';const evidence={snapshot:s,receivedAt:100,transitSeconds:2};
  assert.equal(e.liveFreshness(evidence,200,true).perp,false);assert.equal(e.liveFreshness(evidence,200,true).book,true);
  assert.equal(e.liveFreshness(evidence,200,false).book,false);assert.equal(e.liveFreshness(evidence,99,true).book,false);
  assert.ok(e.liveFreshness(evidence,200,true).ages.l2>=s.status.l2_age_seconds+2);
});
for(const [value,expected] of [['60000.00001','60,000.00001'],['3000.1234','3,000.1234'],['150.0123','150.0123'],[null,'—'],['NaN','—']])test(`financial price ${value}`,()=>assert.equal(f.livePrice(value),expected));
test('raw signed funding and base OI precision are distinct from quote notional',()=>{assert.equal(f.percentage('-.0001',4),'-0.01%');assert.equal(f.liveSize('1.12345',5),'1.12345');assert.equal(f.liveSize('1.1234',4),'1.1234');assert.equal(f.liveSize('1.12',2),'1.12');assert.equal(f.liveSize(null,2),'—');});
test('provider roles preserve one venue, disabled externals and NONE authority',()=>{
  const p=e.checkedLiveProviders(fixture('BTC','providers'),'BTC');
  assert.equal(p.consensus_price,null);assert.equal(p.independent_usable_external_sources,0);
  assert.equal(new Set(p.providers.filter(p=>p.provider.startsWith('HYPERLIQUID')).map(p=>p.independent_source_group)).size,1);
  assert.ok(p.providers.filter(p=>!p.provider.startsWith('HYPERLIQUID')).every(p=>!p.enabled&&p.status==='DISABLED'&&p.price===null));
  assert.equal(p.providers.find(p=>p.provider==='YAHOO_FINANCE').authority,'NONE');
  p.providers[0].mapping.market='ETH';assert.throws(()=>e.checkedLiveProviders(p,'BTC'));
});
const React=require('react'),{renderToStaticMarkup:render}=require('react-dom/server');
const {LiveMarketOrderBook}=load('components/markets/LiveMarketOrderBook.js'),{LivePerpMetrics}=load('components/markets/LivePerpMetrics.js'),{LiveProviderStatus}=load('components/markets/LiveProviderStatus.js');
test('rendered native book uses actual reported levels and labels retained stale evidence',()=>{const s=fixture('SOL');const html=render(React.createElement(LiveMarketOrderBook,{book:s.order_book,decimals:2,current:false,age:40}));assert.match(html,/STALE — LAST OBSERVED/);assert.match(html,/150\.12/);assert.match(html,/1\.23/);assert.match(html,/Source age/);assert.doesNotMatch(html,/FRESH SOURCE/);});
test('rendered stale context does not substitute retained mark or midpoint',()=>{const s=fixture('BTC');const html=render(React.createElement(LivePerpMetrics,{context:s.perp_context,current:false,decimals:5,market:'BTC'}));assert.match(html,/Context stale \/ unavailable/);assert.match(html,/event time UNKNOWN/);assert.doesNotMatch(html,/60,000/);assert.match(html,/Raw venue funding rate/);});
test('provider source age retires old healthy row even while newer selected book remains fresh',()=>{const s=fixture('BTC','providers');const html=render(React.createElement(LiveProviderStatus,{evidence:{health:s,receivedAt:0,transitSeconds:0},now:20000,current:true,bookCurrent:true,perpCurrent:true,bookBudget:10,perpBudget:30}));assert.match(html,/STALE \/ HISTORICAL/);assert.match(html,/Last reported 60,005/);assert.match(html,/Not configured \/ No live evidence/);assert.match(html,/Trading authority NONE/);});
test('API rejects unsupported live market and unbounded history without sending requests',()=>{const {api}=load('api/client.js');for(const m of ['DOGE','btc','BTC-PERP'])assert.throws(()=>api.liveStreamSnapshot(m));for(const limit of [0,1001,Infinity,1.5])assert.throws(()=>api.liveMarketHistory('BTC',limit));});
