const {test} = require('node:test'), assert = require('node:assert/strict'), path = require('node:path');
const React = require('react'), {renderToStaticMarkup} = require('react-dom/server');
const Module = require('node:module'), originalLoad = Module._load;
Module._load = function(name, ...args) { if(name.endsWith('.css')) return {}; return originalLoad.call(this,name,...args); };
const read = p => require(path.join(process.env.TERMINAL_TEST_BUILD,p));
const {shiftDecimal,checkedCatalog,checkedPreview} = read('utils/researchVault.js');
const {useResearchVaultStore:store,capturedResearch} = read('stores/researchVault.js');
const {useTerminalStore:terminal} = read('stores/terminal.js');
const {ResearchPresets} = read('components/vault/ResearchPresets.js');
const {ResearchPreview} = read('components/vault/ResearchPreview.js');
const {api} = read('api/client.js');
Module._load = originalLoad;
const config = () => ({initial_equity_quote:'100000',paper_fee_model_enabled:true,paper_maker_fee_bps:'1',paper_taker_fee_bps:'3',paper_funding_accounting_enabled:false,paper_funding_interval_seconds:3600,max_capital_utilization:'0.75'});
const preset = () => ({preset_id:'balanced-research',name:'Balanced Research',description:'Backend-owned assumption',version:'1',config:config(),config_fingerprint:'a'.repeat(64),limitations:['Hypothetical']});
const proposal = () => ({config:config(),selected_preset_id:'balanced-research'});
const preview = () => ({research_config_version:'phase14-v1',selected_preset_id:'balanced-research',selected_preset_version:'1',normalized_config:config(),config_fingerprint:'a'.repeat(64),customized:false,validation_status:'VALID',simulated:true,baseline_preset_id:'balanced-research',changed_fields:[],baseline_values:config(),custom_values:config(),illustrative_utilization_ceiling_quote:'75000',warnings:[],limitations:['No trades or PnL forecast']});
const reset = () => { store.getState().retireRequest(); store.getState().invalidateEvidence(); store.getState().selectPreset(preset()); };
const render = (C,p) => renderToStaticMarkup(React.createElement(C,p));
for(const [raw,places,want] of [['0.75',2,'75'],['75',-2,'0.75'],['12.3456789123456789',-2,'0.123456789123456789'],['0.000000000000000001',2,'0.0000000000000001'],['100',-2,'1.00'],['-1',-2,'-0.01'],['abc',-2,'abc'],['',-2,'']]) test(`percentage conversion preserves exact ${raw}`,()=>assert.equal(shiftDecimal(raw,places),want));
test('catalog uses backend definitions and rejects duplicate or malformed presets',()=>{
 const catalog={research_config_version:'phase14-v1',simulated:true,presets:[preset()]}; assert.deepEqual(checkedCatalog(catalog),catalog);
 for(const bad of [{...catalog,presets:[preset(),preset()]},{...catalog,simulated:false},{...catalog,presets:[{...preset(),config:{...config(),accounting:{enabled:false}}}]}]) assert.throws(()=>checkedCatalog(bad));
});
test('preview checks response against exact submitted assumptions and selected preset',()=>{
 const p=proposal();p.config.initial_equity_quote='1e5'; p.config.max_capital_utilization='0.7500'; assert.deepEqual(checkedPreview(preview(),p),preview());
 assert.throws(()=>checkedPreview({...preview(),normalized_config:{...config(),initial_equity_quote:'50000'}},p));
 assert.throws(()=>checkedPreview({...preview(),selected_preset_id:'other'},p));
});
for(const patch of [{simulated:false},{validation_status:'UNKNOWN'},{config_fingerprint:'uuid'},{normalized_config:null},{limitations:null},{changed_fields:[{field:'execution_mode'}]},{custom_values:{...config(),paper_maker_fee_bps:'2'}}]) test('malformed preview fails closed '+Object.keys(patch)[0],()=>assert.throws(()=>checkedPreview({...preview(),...patch},proposal())));
test('preset selection and reset preserve decimal strings and in-memory draft',()=>{
 reset();store.getState().edit({initial_equity_quote:'12345.123456789123456789'});assert.equal(store.getState().draftConfig.initial_equity_quote,'12345.123456789123456789');
 store.getState().reset();assert.deepEqual(store.getState().draftConfig,config());
 assert.equal(store.persist,undefined);
});
test('double click admits one preview and an edited draft rejects old completion',()=>{
 reset();const token=store.getState().beginPreview();assert.equal(store.getState().beginPreview(),null);
 store.getState().edit({paper_taker_fee_bps:'20'});assert.equal(store.getState().acceptPreview(token,preview()),false);assert.equal(store.getState().pending,false);
 assert.notEqual(store.getState().validatedVersion,store.getState().draftVersion);
});
test('preset switch invalidates a slow preview',()=>{
 reset();const token=store.getState().beginPreview(); store.getState().selectPreset({...preset(),preset_id:'conservative-capital'});
 assert.equal(store.getState().acceptPreview(token,preview()),false);assert.equal(store.getState().selectedPresetId,'conservative-capital');
});
test('unmounted request cannot replace evidence when a new preview starts',()=>{
 reset();const old=store.getState().beginPreview();store.getState().retireRequest();const fresh=store.getState().beginPreview();
 assert.equal(store.getState().acceptPreview(old,preview()),false);assert.equal(store.getState().pending,true);
 assert.equal(store.getState().acceptPreview(fresh,preview()),true);
});
test('backend disconnect and batched reconnect invalidate preview but preserve draft',()=>{
 reset();const token=store.getState().beginPreview();assert.equal(store.getState().acceptPreview(token,preview()),true);
 const saved={...store.getState().draftConfig}; terminal.getState().setWsState('connected');terminal.getState().setWsState('disconnected');terminal.getState().setWsState('connected');
 assert.equal(store.getState().validatedVersion,null);assert.deepEqual(store.getState().draftConfig,saved);assert.equal(capturedResearch(),null);
});
test('session replacement rejects pending preview',()=>{
 reset();const token=store.getState().beginPreview();const valid=require('./fixtures/terminal-valid.json');
 terminal.setState({terminal:{...structuredClone(valid),process_id:'phase14-test',session_id:'replacement',emitted_at:new Date().toISOString()},wsState:'connected'});
 assert.equal(store.getState().acceptPreview(token,preview()),false);
});
test('selection captures detached research config and survives request retirement/navigation',()=>{
 const valid=require('./fixtures/terminal-valid.json');terminal.setState({terminal:{...structuredClone(valid),process_id:'phase14-test',session_id:'replacement',emitted_at:new Date().toISOString()},wsState:'connected'});
 reset();const token=store.getState().beginPreview();assert.equal(store.getState().acceptPreview(token,preview()),true);store.getState().choose();store.getState().retireRequest();
 const captured=capturedResearch();assert.ok(captured);captured.proposal.config.initial_equity_quote='1';assert.equal(store.getState().lastValidatedConfig.initial_equity_quote,'100000');
 store.getState().edit({initial_equity_quote:'200000'});assert.equal(capturedResearch(),null);
});
test('backend validation error leaves draft unvalidated and preserves returned field error',()=>{
 reset();const token=store.getState().beginPreview();store.getState().failPreview(token,'config.initial_equity_quote: Input should be greater than 0');
 assert.match(store.getState().error,/initial_equity_quote/);assert.notEqual(store.getState().validatedVersion,store.getState().draftVersion);
});
test('preview clearly distinguishes outdated evidence and has no forecast or deployment action',()=>{
 const html=render(ResearchPreview,{preview:preview(),current:false});assert.match(html,/OUTDATED PREVIEW/);assert.match(html,/Revalidate/);assert.match(html,/75000/);assert.match(html,/No trades or PnL forecast/);assert.doesNotMatch(html,/Apply to Strategy|Activate Trading/);
});
test('preset cards show actual backend fees funding utilization and versions',()=>{
 const html=render(ResearchPresets,{presets:[preset()],selected:'balanced-research',onSelect:()=>{}});
 for(const text of ['Balanced Research','100000','1 / 3 bps','configured zero funding','75%','preset v1','aria-pressed="true"']) assert.ok(html.includes(text),text);
});
test('preview API sends decimal strings only to read-only research route',async()=>{
 const old=global.fetch;const seen=[];global.fetch=async(url,init)=>{seen.push({url,init});return {ok:true,status:200,json:async()=>preview()}};
 try{const body=proposal();body.config.initial_equity_quote='12345.123456789123456789'; await api.researchPreview(body);
 assert.equal(seen[0].url,'/api/v1/research-vault/preview');assert.equal(JSON.parse(seen[0].init.body).config.initial_equity_quote,body.config.initial_equity_quote);
 }finally{global.fetch=old;}
});
for(const status of [422,429,503,500]) test(`research API reports actionable ${status}`,async()=>{
 const old=global.fetch;global.fetch=async()=>({ok:false,status,json:async()=>({detail:[{loc:['body','config','initial_equity_quote'],msg:'invalid capital'}]})});
 try{await assert.rejects(api.researchPreview(proposal()),status===429?/capacity is busy/:/invalid capital/);}finally{global.fetch=old;}
});
test('percentage input preserves partial typing while mapping backend fraction exactly once',()=>{
 reset();store.getState().editUtilizationPercent('75.');assert.equal(store.getState().utilizationPercentDraft,'75.');
 store.getState().editUtilizationPercent('75.1234567891234567');assert.equal(store.getState().utilizationPercentDraft,'75.1234567891234567');
 assert.equal(store.getState().draftConfig.max_capital_utilization,'0.751234567891234567');
 store.getState().reset();assert.equal(store.getState().utilizationPercentDraft,'75');
});
test('revalidation retires previous approval even if backend returns a malformed response',()=>{
 reset();let token=store.getState().beginPreview();store.getState().acceptPreview(token,preview());
 token=store.getState().beginPreview();assert.equal(store.getState().validatedVersion,null);store.getState().failPreview(token,'Malformed research preview');
 assert.equal(store.getState().validatedVersion,null);assert.ok(store.getState().preview);
});
