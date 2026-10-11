const {load}=require('./phase153-test-helpers.cjs');
const raw=require('./phase154-fixtures.json');
function fixture(m='BTC') {
  const x=structuredClone(raw[m]);
  const base=Date.parse(x.response.observed.snapshot.status.evaluated_at),delta=Date.now()-base-100;
  function shift(o) {for(const [k,v] of Object.entries(o)) {
    if(typeof v==='string' && /^\d{4}-\d\d-\d\dT/.test(v))o[k]=new Date(Date.parse(v)+delta).toISOString();
    else if(v&&typeof v==='object')shift(v);
  }}
  shift(x.response.observed.snapshot);
  for(const k of ['l2_source_timestamp','l2_observed_at','perp_observed_at'])if(x.response.provenance[k])x.response.provenance[k]=new Date(Date.parse(x.response.provenance[k])+delta).toISOString();
  x.response.generated_at=new Date().toISOString();
  return x;
}
function boundary(req,response){return {market:req.market,liveSelection:0,liveBoundary:0,
  observer:response.observed.snapshot.status.observer_instance_id,generation:response.observed.snapshot.status.connection_generation,
  researchRun:req.research.run_fingerprint,researchDataset:req.research.dataset_fingerprint,researchProfile:req.research.market_profile_fingerprint,
  researchVersion:1,researchEpoch:0,requestGeneration:1};}
function simulation(req){return {...req.research,metrics:req.research.performance,trace:[],research_assumptions:req.research.assumptions,
  vault:{fees_quote:req.research.performance.fees_quote,funding_quote:req.research.performance.funding_quote}};}
module.exports={load,fixture,boundary,simulation};
