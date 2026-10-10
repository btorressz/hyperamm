const {test}=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const read=p=>require(path.join(process.env.TERMINAL_TEST_BUILD,p));
const {checkedMarketCatalog,checkedMarketEvidence}=read('utils/researchMarkets.js');
const {useResearchMarketStore:store,capturedMarket}=read('stores/researchMarkets.js');
const {useResearchVaultStore:vault}=read('stores/researchVault.js');
const {useTerminalStore:terminal}=read('stores/terminal.js');
const {ResearchMarketDetails}=read('components/markets/ResearchMarketDetails.js');
const {api}=read('api/client.js');
const ids=['BTC','ETH','SOL'];
const p=id=>({market:id,display_name:`${id}-PERP`,exchange:'HYPERLIQUID',dex:'',market_type:'PERPETUAL',
 sz_decimals:{BTC:5,ETH:4,SOL:2}[id],asset_index:null,listed:null,research_supported:true,
 metadata_status:'DEMO_PROFILE',metadata_source:'PINNED_RESEARCH_FIXTURE',metadata_observed_at:null,
 metadata_age_seconds:null,unavailable_reason:'Official SDK unavailable',profile_version:'phase146-v1',
 profile_fingerprint:{BTC:'a',ETH:'b',SOL:'c'}[id].repeat(64),simulated_reference_price:{BTC:'60000',ETH:'3000',SOL:'150'}[id],
 research_price_rules:'At most 5 significant figures and 6 - szDecimals decimal places; integer exception.',
 limitations:['Simulated fixture; listing unverified','PAPER research only']});
const catalog=()=>({catalog_version:'phase146-v1',research_only:true,execution_mode:'PAPER',markets:ids.map(p)});
const reset=()=>{store.getState().invalidate();store.getState().selectMarket('ETH');store.getState().acceptCatalog(catalog(),store.getState().evidenceEpoch);};
const evidence=p=>({research_market:p.market,market_profile_fingerprint:p.profile_fingerprint,
 market_profile_version:p.profile_version,metadata_status:p.metadata_status,metadata_source:p.metadata_source});
test('fresh research preference is ETH and lives outside terminal strategy',()=>{
 assert.equal(store.getState().selectedResearchMarket,'ETH');assert.equal(store.persist,undefined);
 assert.equal(store.getState().catalog,null);
});
test('bounded catalog accepts exactly BTC ETH SOL and detached validated profiles',()=>{
 reset();const c=catalog();assert.deepEqual(checkedMarketCatalog(c),c);
 const selected=capturedMarket();selected.sz_decimals=6;assert.equal(capturedMarket().sz_decimals,4);
});
for(const patch of [{research_only:false},{execution_mode:'TESTNET'},{markets:[]},{markets:[p('BTC'),p('ETH')]},
 {markets:[p('BTC'),p('ETH'),p('ETH')]},{markets:[p('BTC'),p('ETH'),{...p('SOL'),market:'DOGE'}]}])
 test('malformed or unsupported catalog rejected '+JSON.stringify(patch),()=>assert.throws(()=>checkedMarketCatalog({...catalog(),...patch})));
for(const patch of [{metadata_status:'VERIFIED'},{sz_decimals:7},{sz_decimals:'4'},{dex:'hip3'},
 {market_type:'SPOT'},{profile_fingerprint:'invalid'},{simulated_reference_price:'NaN'},
 {asset_index:1},{listed:true},{metadata_source:'OFFICIAL_SDK_NATIVE_META'},{metadata_observed_at:'2026-01-01'}])
 test('DEMO fixture cannot claim exchange facts '+JSON.stringify(patch),()=>{
  const c=catalog();c.markets[1]={...p('ETH'),...patch};assert.throws(()=>checkedMarketCatalog(c));
 });
test('verified catalog requires official provenance timestamp listing and native index',()=>{
 const c=catalog();c.markets=c.markets.map((p,i)=>({...p,metadata_status:'EXCHANGE_VERIFIED',
  metadata_source:'OFFICIAL_SDK_NATIVE_META',metadata_observed_at:'2026-10-10T00:00:00Z',metadata_age_seconds:2,listed:true,asset_index:i}));
 assert.deepEqual(checkedMarketCatalog(c),c);
 for(const patch of [{asset_index:null},{asset_index:-1},{listed:false},{metadata_observed_at:null},{metadata_age_seconds:-1}]){
  const bad=structuredClone(c);Object.assign(bad.markets[0],patch);assert.throws(()=>checkedMarketCatalog(bad));
 }
});
for(const id of ids) test(id+' selection shared across workspaces preserves runtime and accounting draft',()=>{
 reset();const before=structuredClone(terminal.getState().terminal);
 vault.setState({draftConfig:{initial_equity_quote:'12345'},validatedVersion:1,draftVersion:1,useForResearch:true});
 store.getState().selectMarket(id);assert.equal(capturedMarket().market,id);
 assert.deepEqual(terminal.getState().terminal,before);assert.equal(vault.getState().draftConfig.initial_equity_quote,'12345');
 if(id!=='ETH'){assert.equal(vault.getState().validatedVersion,null);assert.equal(vault.getState().useForResearch,false);}
});
for(const id of ['btc','BTC-PERP','HYPE','foo:SOL','SOL/USDC']) test('selector rejects '+id,()=>assert.throws(()=>store.getState().selectMarket(id)));
test('market switch during catalog loading resolves current asset rather than prior selection',()=>{
 reset();store.getState().invalidate();const epoch=store.getState().evidenceEpoch;store.getState().selectMarket('BTC');
 assert.equal(capturedMarket(),null);assert.equal(store.getState().acceptCatalog(catalog(),epoch),true);
 assert.equal(capturedMarket().market,'BTC');
});
test('disconnect and batched reconnect retire catalog while preserving local preference',()=>{
 reset();store.getState().selectMarket('SOL');const epoch=store.getState().evidenceEpoch;
 terminal.getState().setWsState('connected');terminal.getState().setWsState('disconnected');terminal.getState().setWsState('connected');
 assert.equal(capturedMarket(),null);assert.equal(store.getState().selectedResearchMarket,'SOL');
 assert.equal(store.getState().acceptCatalog(catalog(),epoch),false);
});
test('backend session replacement rejects stale profile evidence',()=>{
 reset();const epoch=store.getState().evidenceEpoch;
 terminal.setState({terminal:{...structuredClone(require('./fixtures/terminal-valid.json')),process_id:'phase146-new'}});
 assert.equal(capturedMarket(),null);assert.equal(store.getState().acceptCatalog(catalog(),epoch),false);
});
test('unavailable market cannot be captured for research',()=>{
 reset();const c=catalog();c.markets[1]={...p('ETH'),metadata_status:'UNAVAILABLE',research_supported:false,sz_decimals:null};
 store.getState().acceptCatalog(c,store.getState().evidenceEpoch);assert.equal(capturedMarket(),null);
});
test('completed result retains BTC after SOL switch and mismatched evidence fails closed',()=>{
 reset();store.getState().selectMarket('BTC');const captured=capturedMarket(),result=evidence(captured);
 store.getState().selectMarket('SOL');assert.equal(checkedMarketEvidence(result,captured).research_market,'BTC');
 assert.throws(()=>checkedMarketEvidence(result,capturedMarket()));
 assert.equal(result.research_market,'BTC');
});
for(const key of ['research_market','market_profile_fingerprint','market_profile_version','metadata_status','metadata_source'])
 test('response cannot substitute captured '+key,()=>assert.throws(()=>checkedMarketEvidence({...evidence(p('BTC')),[key]:'changed'},p('BTC'))));
test('profile refresh retires prior market-dependent accounting approval',()=>{
 reset();vault.setState({validatedVersion:1,useForResearch:true});const c=catalog();c.markets[1].profile_fingerprint='d'.repeat(64);
 store.getState().acceptCatalog(c,store.getState().evidenceEpoch);assert.equal(vault.getState().validatedVersion,null);
});
for(const id of ids) test(id+' details label hypothetical anchors precision and simulated metadata',()=>{
 const html=renderToStaticMarkup(React.createElement(ResearchMarketDetails,{profile:p(id)}));
 for(const text of [`${id}-PERP`,'SIMULATED METADATA','fixed research anchor','Size precision','PAPER / SIMULATED','unverified'])assert.ok(html.includes(text),text);
 assert.doesNotMatch(html,/EXCHANGE-VERIFIED METADATA|Activate Market|Trade BTC|Enable Live/);
});
test('verified details identify actual source and index',()=>{
 const html=renderToStaticMarkup(React.createElement(ResearchMarketDetails,{profile:{...p('BTC'),metadata_status:'EXCHANGE_VERIFIED',metadata_source:'OFFICIAL_SDK_NATIVE_META',asset_index:2,listed:true}}));
 assert.match(html,/EXCHANGE-VERIFIED METADATA/);assert.match(html,/OFFICIAL_SDK_NATIVE_META/);
});
test('research catalog API is read-only and never writes strategy',async()=>{
 const old=global.fetch,calls=[];global.fetch=async(url,init)=>{calls.push({url,init});return {ok:true,status:200,json:async()=>catalog()}};
 try{await api.researchMarkets();assert.equal(calls[0].url,'/api/v1/research-markets');assert.equal(calls[0].init.method,undefined);}
 finally{global.fetch=old;}
});
