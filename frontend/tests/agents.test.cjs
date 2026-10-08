const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const {AgentPanel}=require(path.join(process.env.TERMINAL_TEST_BUILD,'components/AgentPanel.js'));
const {validateTerminal}=require(path.join(process.env.TERMINAL_TEST_BUILD,'utils/validateTerminal.js'));
const valid=require('./fixtures/terminal-valid.json');
function shadowFrame(){
 const frame=structuredClone(valid);
 const shadow={...frame.agents.regime,agent:'PREDICTIVE_ADVERSE_SELECTION',state:'PREDICTED',mode:'SHADOW',
   affects_quotes:false,spread_multiplier:'1',bid_size_multiplier:'1',ask_size_multiplier:'1',max_levels:null,
   metrics:{bid_adverse_probability:'0.8',ask_adverse_probability:'0.2',inference_confidence:'1',
      markout_horizon_seconds:'5',last_inference_time:frame.emitted_at},model_provenance:null,
   feature_schema_version:'passive-adverse-v1'};
 for(const field of ['direction','momentum_bps','realized_volatility','volatility_score','book_imbalance',
    'trend_strength','funding_stress_score','basis_stress_score','book_pressure_score','inventory_stress_score']) delete shadow[field];
 frame.agents.predictive_adverse_selection=shadow;
 frame.agents.supervisor.predictive_adverse_selection=structuredClone(shadow);
 return frame;
}
test('expanded cards label supervisory evidence and shadow authority truthfully',()=>{
 const frame=shadowFrame();validateTerminal(frame);
 const html=renderToStaticMarkup(React.createElement(AgentPanel,{t:frame}));
 for(const label of ['LIQUIDITY QUALITY','PERP CROWDING','ML SHADOW','NO QUOTE AUTHORITY','HEURISTIC','DETERMINISTIC','SIMULATED','conditional on fill']) assert.ok(html.includes(label),label);
 assert.ok(html.includes('passive-adverse-v1'));
 assert.ok(!html.includes('AI trades')&&!html.includes('predictive PnL'));
});
test('wire contract rejects predictive authority, nonfinite and out of range probability',()=>{
 for(const probability of ['NaN','Infinity','-0.1','1.1',0.8]) {
  const frame=shadowFrame();frame.agents.predictive_adverse_selection.metrics.bid_adverse_probability=probability;
  assert.throws(()=>validateTerminal(frame),/Invalid/);
 }
 const frame=shadowFrame();frame.agents.predictive_adverse_selection.affects_quotes=true;
 assert.throws(()=>validateTerminal(frame),/Invalid/);
 const widened=shadowFrame();widened.agents.predictive_adverse_selection.spread_multiplier='1.2';
 assert.throws(()=>validateTerminal(widened),/Invalid/);
});
test('missing shadow evidence renders unavailable values',()=>{
 const html=renderToStaticMarkup(React.createElement(AgentPanel,{t:valid}));
 assert.ok(html.includes('ML SHADOW')&&html.includes('UNAVAILABLE'));
});
