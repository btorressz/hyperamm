const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {load,fixture,simulation,boundary}=require('./phase154-test-helpers.cjs');
const s=load('stores/marketResearchComparison.js').useMarketResearchComparisonStore;
const root=path.resolve(__dirname,'../src');
test('three detached completed summaries maximum; no original or Vault mutation',()=>{
 s.setState({results:[],selectedId:'',version:0,artifact:null});
 for(const m of ['BTC','ETH','SOL','BTC']){const f=fixture(m),result=simulation(f.request),before=structuredClone(result);s.getState().retain(result);assert.deepEqual(result,before);result.research_assumptions.midpoint='1';assert.notEqual(s.getState().results[0].research.assumptions.midpoint,'1');}
 assert.equal(s.getState().results.length,3);
});
test('market identity never relabeled on selection and frozen artifact retirement',()=>{
 const f=fixture();s.setState({results:[],selectedId:'',version:0,artifact:null});s.getState().retain(simulation(f.request));s.getState().select(f.request.research.run_fingerprint);
 s.getState().freeze({data:f.response,boundary:boundary(f.request,f.response),receivedAt:0,historicalReason:null});
 s.getState().select('');assert.equal(s.getState().artifact.data.research.research_market,'BTC');assert.ok(s.getState().artifact.historicalReason);
});
test('new research retires captured artifact; historical state is sticky',()=>{
 const f=fixture('ETH');s.getState().retain(simulation(f.request));s.getState().retire('reconnect');const reason=s.getState().artifact.historicalReason;
 s.getState().retire('new fresh tick');assert.equal(s.getState().artifact.historicalReason,reason);
});
for(const file of ['stores/marketResearchComparison.ts','hooks/useMarketResearchComparison.ts','components/research-comparison/MarketResearchWorkspace.tsx'])test(`comparison ${file} has no writes to trading or research execution`,()=>{
 const source=fs.readFileSync(path.join(root,file),'utf8');
 for(const forbidden of ['updateStrategy','startStrategy','optimizeSimulation','runSimulation','localStorage','sessionStorage','useResearchVaultStore','deploy','placeOrder'])assert.equal(source.includes(forbidden),false,forbidden);
});
test('request uses abort and TanStack, no retry or polling comparison',()=>{
 const source=fs.readFileSync(path.join(root,'hooks/useMarketResearchComparison.ts'),'utf8');assert.match(source,/useMutation/);assert.match(source,/AbortController/);assert.match(source,/retry:false/);assert.doesNotMatch(source,/refetchInterval/);
});
