const {test}=require('node:test'),assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const read=p=>require(path.join(process.env.TERMINAL_TEST_BUILD,p));
const Module=require('node:module'),original=Module._load;
Module._load=function(name,...args){
 if(name.endsWith('.css'))return {};
 if(name==='lightweight-charts')return original.call(this,path.resolve(__dirname,'../node_modules/lightweight-charts/dist/lightweight-charts.development.mjs'),...args);
 return original.call(this,name,...args);
};
const u=read('utils/portfolioResearch.js'),{createPortfolioStore,usePortfolioResearchStore}=read('stores/portfolioResearch.js');
const {PortfolioConfiguration}=read('components/portfolio/PortfolioConfiguration.js');
const {PortfolioStressLab}=read('components/portfolio/PortfolioStressLab.js');
const {PortfolioAnalytics,PortfolioRiskPanel,PortfolioEquityChart,PortfolioResearchStatus,PortfolioStressComparison}=read('components/portfolio/PortfolioAnalytics.js');
const {PortfolioProvenance}=read('components/portfolio/PortfolioProvenance.js');
const {useTerminalStore}=read('stores/terminal.js');const {api}=read('api/client.js');
const {terminalPages,pageFromHash}=read('utils/navigation.js');
Module._load=original;
const native=require('./fixtures/portfolio-native.json'),clone=x=>structuredClone(x),render=(C,p)=>renderToStaticMarkup(React.createElement(C,p));
const q=()=>({mode:'STRESS',config:native.preview.config,config_fingerprint:native.preview.config_fingerprint,risk_policy:native.preview.risk_policy,scenario:native.preview.stress});
const leg=()=>clone(native.result.baseline);

test('dedicated bookmarkable portfolio research route shares native registry',()=>{
 assert.equal(pageFromHash('#/portfolio-research'),'Portfolio Research');assert.equal(terminalPages.filter(p=>p.slug==='portfolio-research').length,1);
 const source=fs.readFileSync(path.join(__dirname,'../src/App.tsx'),'utf8');assert.match(source,/page === 'Portfolio Research' \? <PortfolioResearch/);
});
for(const count of [1,2,3])test(`${count}-market exact allocation form validates`,()=>{
 const d=u.initialDraft();d.allocations=d.allocations.slice(0,count);assert.equal(u.allocationError(d),null);assert.equal(u.draftRequest(d).allocations.length,count);
});
for(const [name,patch] of [
 ['negative',d=>d.allocations[0].allocated_equity_quote='-1'],['overbudget',d=>d.budget.total_equity_quote='1'],['duplicate',d=>d.allocations[1]=d.allocations[0]],
 ['unsupported',d=>d.allocations[0].market='DOGE'],['empty',d=>d.allocations=[]],['reserve',d=>d.budget.minimum_reserve_quote='5000.000000000000000001'],
 ['binary notation',d=>d.allocations[0].allocated_equity_quote='1e3'],['zero',d=>d.allocations[0].allocated_equity_quote='0'],['precision',d=>d.allocations[0].allocated_equity_quote='1.0000000000000000001']
])test(`invalid ${name} draft cannot prepare execution`,()=>{const d=u.initialDraft();patch(d);assert.ok(u.allocationError(d));assert.throws(()=>u.draftRequest(d));});
test('allocation checks retain exact 18-place budget boundaries beyond binary precision',()=>{
 const d=u.initialDraft();d.budget.total_equity_quote='100000.000000000000000001';d.budget.minimum_reserve_quote='5000.000000000000000001';assert.equal(u.allocationError(d),null);
 assert.equal(u.exactInput('9007199254740993.000000000000000001'),9007199254740993000000000000000001n);
});
for(const kind of Object.keys(u.stressKinds))test(`${kind} has scenario-specific bounded form and request`,()=>{
 const d=u.initialDraft();d.stressEnabled=true;d.stressKind=kind;const req=u.draftRequest(d);assert.equal(req.stress.scenario_type,kind);assert.equal(req.stress.selected_markets.length,3);
 const html=render(PortfolioStressLab,{d,edit:()=>{}});assert.match(html,/Stress scenario/);assert.match(html,/NOT EMPIRICAL CORRELATION/);assert.doesNotMatch(html,/<textarea/);
 if(kind==='FUNDING_STRESS')assert.match(html,/signed funding adjustment/);
 if(kind==='ORACLE_DEGRADATION'){assert.match(html,/Stale oracle timestamps are not supported/);assert.match(html,/value="LINEAR_TO_BASELINE" disabled/);}
 if(kind==='CONCENTRATION_STRESS')assert.match(html,/largest validated pre-onset position exposure/);
});
test('missing oracle mode excludes hidden divergence from request',()=>{
 const d=u.initialDraft();d.stressEnabled=true;d.stressKind='ORACLE_DEGRADATION';assert.equal(u.draftRequest(d).stress.assumptions.reference_divergence_fraction,undefined);
 d.stressFields.reference_mode='DIVERGENT';assert.equal(u.draftRequest(d).stress.assumptions.reference_divergence_fraction,'0.1');
});
test('server preview retains exact server-generated fingerprint and canonical capture',()=>{
 const p=u.checkedPreview(native.preview,native.draft);assert.equal(p.config_fingerprint,native.preview.config_fingerprint);assert.equal(p.config.scenarios[0].captured.canonical_json,native.preview.config.scenarios[0].captured.canonical_json);
});
for(const corruption of ['fingerprint','authority','capital','market','frames'])test(`preview rejects mismatched ${corruption}`,()=>{
 const p=clone(native.preview);if(corruption==='fingerprint')p.config_fingerprint='client-generated';
 if(corruption==='authority')p.authority='LIVE';if(corruption==='capital')p.config.budget.total_equity_quote='1';
 if(corruption==='market')p.config.allocations[0].market='SOL';if(corruption==='frames')p.config.scenarios[0].frames++;
 assert.throws(()=>u.checkedPreview(p,native.draft));
});
test('native terminal projection binds preview and result sources',()=>{assert.equal(u.checkedTerminal(native.result,q()),native.result);});
for(const corruption of ['authority','fingerprint','chart source','temporal','sequence','endpoint'])test(`terminal rejects ${corruption} substitution`,()=>{
 const r=clone(native.result);if(corruption==='authority')r.read_only=false;if(corruption==='fingerprint')r.config_fingerprint='a'.repeat(64);
 if(corruption==='chart source')r.baseline.charts.analysis_fingerprint='a'.repeat(64);
 if(corruption==='temporal')r.baseline.temporal.classification='FINAL_ONLY';
 if(corruption==='sequence')r.baseline.charts.points[1].sequence=1;
 if(corruption==='endpoint')r.baseline.charts.equity_series_fingerprint='b'.repeat(64);
 assert.throws(()=>u.checkedTerminal(r,q()));
});
for(const decision of ['NORMAL','WARN','REDUCE','HALT'])test(`actual risk ${decision} renders distinct post-execution assessment`,()=>{
 const b=leg();b.risk.outcome='ASSESSED';b.risk.decision=decision;const html=render(PortfolioRiskPanel,{leg:b,label:'Baseline'});
 assert.match(html,new RegExp(decision));assert.match(html,/post-execution research assessments/);assert.match(html,/Observed/);assert.match(html,/Ceiling/);
});
test('BLOCKED cannot appear NORMAL; known HALT remains alongside incomplete evidence',()=>{
 const b=leg();b.risk.outcome='BLOCKED';b.risk.decision=null;assert.equal(u.riskState(b.risk),'BLOCKED');
 b.risk.decision='HALT';assert.equal(u.riskState(b.risk),'BLOCKED · known HALT');const html=render(PortfolioRiskPanel,{leg:b,label:'Baseline'});assert.match(html,/BLOCKED · known HALT/);assert.match(html,/incomplete evaluation/);
});
for(const classification of ['MODELED_ALIGNED','FINAL_ONLY','INCOMPARABLE','UNAVAILABLE'])test(`${classification} accounting and chart availability are explicit`,()=>{
 const b=leg();b.temporal.classification=classification;const html=render(PortfolioResearchStatus,{leg:b,label:'Baseline'});assert.match(html,new RegExp(classification));assert.match(html,/UNVERIFIED/);
 if(classification!=='MODELED_ALIGNED'){b.charts.status='UNAVAILABLE';b.charts.points=[];b.charts.reason=classification;const chart=render(PortfolioEquityChart,{leg:b,label:'Baseline',metric:'equity_quote'});assert.match(chart,/Unavailable/);assert.doesNotMatch(chart,/<canvas/);}
});
test('missing values remain Unavailable and never an invented zero drawdown',()=>{
 assert.equal(u.decimalDisplay(null),'Unavailable');assert.equal(u.fractionDisplay(undefined),'Unavailable');assert.equal(u.fractionDisplay('0.123456'),'12.3456 %');
 const b=leg();b.accounting.drawdown=null;b.accounting.equity_quote=null;const r={...native.result,baseline:b};const html=render(PortfolioAnalytics,{result:r});assert.match(html,/Unavailable/);
});
test('baseline stress differences use backend eligibility with no missing delta as zero',()=>{
 const r=clone(native.result);r.metrics.comparisons[0].difference=null;r.metrics.comparisons[0].status='UNAVAILABLE';
 const html=render(PortfolioStressComparison,{result:r});assert.match(html,/Baseline/);assert.match(html,/Stressed/);assert.match(html,/Difference/);assert.match(html,/Unavailable/);assert.match(html,/reported by Python/);
});
test('provenance shows source/result/accounting fingerprints and honest authority labels',()=>{
 const html=render(PortfolioProvenance,{preview:native.preview,result:native.result});for(const word of ['Configuration fingerprint','Original result fingerprint','Accounting fingerprint','HISTORICAL SYNCHRONIZATION UNVERIFIED','NOT EMPIRICAL CORRELATION','not cryptographic signatures','Copy'])assert.ok(html.includes(word),word);
});
test('allocation and stress controls have labeled keyboard-native fields',()=>{
 const html=render(PortfolioConfiguration,{d:u.initialDraft(),edit:()=>{},preview:null,scenarios:[]});assert.match(html,/BTC allocation \(USDC\)/);assert.match(html,/type="checkbox"/);assert.match(html,/<label>/);assert.match(html,/Portfolio Risk Controls/);assert.match(html,/Percentage requires preview/);
});
for(const change of ['capital','market','risk','stress'])test(`${change} edit retires accepted evidence and pending requests`,()=>{
 const store=createPortfolioStore();const token=store.getState().begin();store.getState().acceptPreview(token,native.preview);const run=store.getState().begin();
 store.getState().edit(d=>({...d,...(change==='capital'?{frames:'121'}:change==='market'?{allocations:d.allocations.slice(0,1)}:change==='risk'?{risk_limits:{...d.risk_limits,max_drawdown_fraction:'0.1'}}:{stressEnabled:true})}));
 assert.equal(store.getState().preview,null);assert.equal(store.getState().result,null);assert.equal(store.getState().acceptResult(run,native.result),false);
});
test('request identity suppresses old completions and old failures after newer acceptance',()=>{
 const store=createPortfolioStore(),old=store.getState().begin();store.getState().invalidate();const next=store.getState().begin();store.getState().acceptResult(next,native.result);
 assert.equal(store.getState().acceptPreview(old,native.preview),false);store.getState().fail(old,'stale failure');assert.equal(store.getState().error,'');assert.equal(store.getState().result,native.result);
});
test('disconnection and reconnection never restore accepted evidence',()=>{
 const old=useTerminalStore.getState();try{
 useTerminalStore.getState().setWsState('connected');const store=usePortfolioResearchStore;const token=store.getState().begin();store.getState().acceptPreview(token,native.preview);
 useTerminalStore.getState().setWsState('disconnected');assert.equal(store.getState().preview,null);
 useTerminalStore.getState().setWsState('connected');assert.equal(store.getState().preview,null);
 const t=store.getState().begin();assert.ok(t); // local REST research can proceed without a current WS snapshot.
 store.getState().invalidate();assert.equal(store.getState().acceptResult(t,native.result),false);
 }finally{useTerminalStore.setState(old);usePortfolioResearchStore.getState().invalidate();}
});
for(const status of [429,413,422,503,500])test(`HTTP ${status} gives sanitized portfolio guidance`,async()=>{
 const originalFetch=global.fetch;global.fetch=async()=>new Response(JSON.stringify({detail:'SECRET /private/traceback'}),{status});
 try{await assert.rejects(api.portfolioTerminal(q()),e=>{assert.ok(e.message.includes(String(status)));assert.doesNotMatch(e.message,/SECRET|private|traceback/);assert.match(e.message,/cancellation does not stop/);return true;});}finally{global.fetch=originalFetch;}
});
test('portfolio API sends exact validated configuration and abort signal once',async()=>{
 const originalFetch=global.fetch,controller=new AbortController();let count=0;global.fetch=async(url,init)=>{count++;assert.equal(url,'/api/v1/portfolio-research/terminal');assert.equal(init.signal,controller.signal);assert.deepEqual(JSON.parse(init.body),q());return new Response(JSON.stringify(native.result),{status:200});};
 try{await api.portfolioTerminal(q(),controller.signal);assert.equal(count,1);}finally{global.fetch=originalFetch;}
});
test('portfolio API bounds bytes before JSON parsing',async()=>{
 const originalFetch=global.fetch;global.fetch=async()=>new Response(' '.repeat(200001),{status:200});
 try{await assert.rejects(api.portfolioTerminal(q()),/budget/);}finally{global.fetch=originalFetch;}
});
test('no automatic execution, live calls, polling or browser persistence in portfolio workspace',()=>{
 const files=['pages/PortfolioResearch.tsx','hooks/usePortfolioResearch.ts','stores/portfolioResearch.ts','components/portfolio/PortfolioStressLab.tsx'];
 const source=files.map(p=>fs.readFileSync(path.join(__dirname,'../src',p),'utf8')).join('\n');
 assert.doesNotMatch(source,/api\.(start|updateStrategy|kill|resume)|localStorage|sessionStorage|refetchInterval|setInterval/);assert.match(source,/retry:\s*false/);assert.match(source,/AbortController/);assert.match(source,/Stop\s+waiting\s+aborts/);
});
test('disconnected reconnect attempts leave local REST evidence usable',()=>{
 const previous=useTerminalStore.getState();try{
 useTerminalStore.getState().setWsState('disconnected');const s=usePortfolioResearchStore;const t=s.getState().begin();s.getState().acceptPreview(t,native.preview);
 for(const ws of ['connecting','disconnected','connecting','error'])useTerminalStore.getState().setWsState(ws);
 assert.equal(s.getState().preview,native.preview);
 }finally{useTerminalStore.setState(previous);usePortfolioResearchStore.getState().invalidate();}
});
