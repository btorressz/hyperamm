const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const {effectiveLiquidity}=require(path.join(process.env.TERMINAL_TEST_BUILD,'utils/effectiveLiquidity.js'));
const {EffectiveLiquidity}=require(path.join(process.env.TERMINAL_TEST_BUILD,'components/EffectiveLiquidity.js'));
const {QuoteDistribution,LiquidityDistributionChart}=require(path.join(process.env.TERMINAL_TEST_BUILD,'components/LiquidityDistributionChart.js'));
const valid=require('./fixtures/terminal-valid.json');
function quote(side,index,price,size='0.1'){return {side,level_index:index,price,size,distance_bps:'0.3333',source_model:'CONSTANT_PRODUCT',state:'DESIRED'};}
const collapsed=['BID','ASK'].flatMap(side=>Array.from({length:50},(_,i)=>quote(side,i,side==='BID'?'2999.9':'3000.1')));
const render=(Component,props)=>renderToStaticMarkup(React.createElement(Component,props));
test('100 slots produce two groups with exact sums and complete lineage',()=>{
 const before=JSON.stringify(collapsed), d=effectiveLiquidity(collapsed);
 assert.equal(d.logical_slots,100); assert.equal(d.price_groups.length,2);
 assert.equal(d.effective_bid_levels,1);assert.equal(d.effective_ask_levels,1);
 for(const g of d.price_groups){assert.equal(g.quantity,'5.0');assert.equal(g.level_indices.length,50);assert.deepEqual(g.level_indices,Array.from({length:50},(_,i)=>i));}
 assert.deepEqual(d.price_groups.map(g=>g.notional),['15000.50','14999.50']);
 assert.equal(JSON.stringify(collapsed),before);
});
test('same tick decimal spellings aggregate without binary floating point',()=>{
 const d=effectiveLiquidity([quote('BID',0,'0.3','0.1'),quote('BID',1,'3e-1','0.2'),quote('BID',2,'0.3000','0.3')]);
 assert.equal(d.price_groups.length,1);assert.equal(d.price_groups[0].quantity,'0.6');assert.equal(d.price_groups[0].notional,'0.18');
});
test('distinct Decimal ticks that share a Number are not coalesced',()=>{
 const d=effectiveLiquidity([quote('BID',0,'2999.90000000000000001'),quote('BID',1,'2999.90000000000000002')]);
 assert.equal(d.price_groups.length,2);
});
test('no collapse and partial collapse have accurate counts',()=>{
 const q=[quote('BID',0,'2999'),quote('BID',1,'2998'),quote('ASK',0,'3001')];
 assert.equal(effectiveLiquidity(q).warnings.length,0);
 const d=effectiveLiquidity([...q,quote('BID',2,'2999')]);
 assert.equal(d.price_groups.length,3);assert.equal(d.warnings.length,1);
});
test('suppressed slots are absent from the authorized view',()=>{
 const d=effectiveLiquidity(collapsed.filter(q=>q.side==='ASK'&&q.level_index<2));
 assert.equal(d.logical_slots,2);assert.equal(d.effective_bid_levels,0);assert.equal(d.price_groups.length,1);
});
for(const mutation of [{price:'0'},{size:'NaN'},{side:'OTHER'}])test(`invalid evidence ${JSON.stringify(mutation)} reports no active depth`,()=>{
 const q=[{...quote('BID',0,'2999'),...mutation}];assert.equal(effectiveLiquidity(q).available,false);
 assert.ok(render(EffectiveLiquidity,{quotes:q}).includes('unavailable'));
});
test('crossed ladders and duplicate slots fail observational validation',()=>{
 for(const q of [[quote('BID',0,'3001'),quote('ASK',0,'3000')],[quote('BID',0,'2999'),quote('BID',0,'2998')]]){
  assert.equal(effectiveLiquidity(q).available,false);assert.equal(effectiveLiquidity(q).price_groups.length,0);
 }
});
test('grouped rendering uses aggregate bar sizes and preserves observational controls',()=>{
 const html=render(QuoteDistribution,{quotes:collapsed});assert.equal((html.match(/<rect/g)||[]).length,2);
 assert.ok(html.includes('aggregate size 5'));assert.ok(html.includes('Aggregate quote size at executable tick'));
 const info=render(EffectiveLiquidity,{quotes:collapsed,configured:50});
 for(const expected of ['Configured levels per side: 50','quote slots: 100','Distinct BID prices: 1','Distinct ASK prices: 1','50 logical BID slots produced 1','observational','Resting venue quantities'])assert.ok(info.includes(expected),expected);
 assert.ok(!info.includes('<button'));
});
test('missing optional diagnostics and empty quotes render without inventing depth',()=>{
 assert.ok(render(EffectiveLiquidity,{quotes:[]}).includes('quote slots: 0'));
 assert.ok(render(QuoteDistribution,{quotes:[]}).includes('No quote evidence'));
 const t={...valid,authorized_quotes:collapsed,strategy_quotes:collapsed};
 const html=render(LiquidityDistributionChart,{t});
 assert.ok(html.includes('Neutral AMM'));assert.ok(html.includes('mathematical curve sampling'));
 assert.ok(html.includes('upstream suppressed levels are unavailable'));
});
