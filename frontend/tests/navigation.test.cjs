const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const compiled=name=>require(path.join(process.env.TERMINAL_TEST_BUILD,name));
const {terminalPages,pageFromHash,pageHref,subscribeNavigation,normalizePageHash,workspaceHref,workspaceFromHash,navigationGroups,experienceModes}=compiled('utils/navigation.js');
const {Sidebar}=compiled('components/Sidebar.js');
const {Header}=compiled('components/Header.js');
const {terminalObservationIsCurrent}=compiled('utils/freshness.js');
const {Panel,Empty,Loading,StatusBanner}=compiled('components/TerminalPrimitives.js');
const {useDisplayStore}=compiled('stores/display.js');
const valid=require('./fixtures/terminal-valid.json');
const render=(Component,props)=>renderToStaticMarkup(React.createElement(Component,props));
const sidebar=(props={})=>render(Sidebar,{page:'Risk',t:valid,ws:'connected',mobile:false,open:false,onClose:()=>{},...props});
const header=(t, ws)=>render(Header,{t,ws,historical:!terminalObservationIsCurrent(t,ws),
 backendHealthFailed:false,navigationOpen:false,onOpenNavigation:()=>{}});

test('all thirteen pages round-trip through distinct bookmarkable URLs',()=>{
 assert.equal(terminalPages.length,13);
 assert.equal(new Set(terminalPages.map(p=>p.slug)).size,13);
 for(const {name} of terminalPages) assert.equal(pageFromHash(pageHref(name)),name);
});
test('unknown, malformed and empty routes fall back safely',()=>{
 for(const hash of ['', '#', '#/unknown', '#/risk/extra', '#/%ZZ', '#/Risk', '#page-content']) assert.equal(pageFromHash(hash),'Dashboard');
});
test('fallback normalization replaces one entry and preserves history state',()=>{
 const original=global.window, calls=[];
 global.window={location:{hash:'#/invalid'},history:{state:{existing:1},replaceState(...args){calls.push(args);global.window.location.hash=args[2];}}};
 try { normalizePageHash(); normalizePageHash(); assert.deepEqual(calls,[[{existing:1},'', '#/dashboard']]); }
 finally {global.window=original;}
});
test('route subscriptions track hash/history changes and clean up ownership',()=>{
 const original=global.window, target=new EventTarget();let count=0;
 global.window=target;
 try {const off=subscribeNavigation(()=>count++);target.dispatchEvent(new Event('hashchange'));assert.equal(count,1);off();target.dispatchEvent(new Event('hashchange'));assert.equal(count,1);}
 finally {global.window=original;}
});
test('sidebar has thirteen native links and exactly one active accessible page',()=>{
 const html=sidebar();
 for (const {name} of terminalPages) {
   assert.equal((html.match(new RegExp(`href="${pageHref(name)}"`, 'g')) || []).length, 1);
 }
 assert.equal((html.match(/aria-current="page"/g)||[]).length,1);
 assert.match(html,/href="#\/risk"[^>]*aria-label="Risk"[^>]*aria-current="page"/);
 assert.match(html,/aria-label="Terminal pages"/);assert.match(html,/aria-label="Collapse navigation"/);
});
test('sidebar collapse preference preserves density and history preferences',()=>{
 const previous=useDisplayStore.getState();
 try {previous.setSidebarCollapsed(true);const next=useDisplayStore.getState();assert.equal(next.sidebarCollapsed,true);assert.equal(next.dense,previous.dense);assert.equal(next.historySize,previous.historySize);assert.equal(next.defaultRange,previous.defaultRange);}
 finally {useDisplayStore.setState(previous);}
});
test('mobile drawer uses modal semantics when open and is inert when closed',()=>{
 const closed=sidebar({mobile:true});assert.match(closed,/inert=""/);assert.doesNotMatch(closed,/aria-modal/);
 const open=sidebar({mobile:true,open:true});assert.match(open,/role="dialog"/);assert.match(open,/aria-modal="true"/);assert.doesNotMatch(open,/inert=""/);
});
test('sidebar identifies retained system evidence as historical',()=>{
 assert.match(sidebar({ws:'disconnected'}),/historical/);
});
test('shared panel has a named section and semantic heading',()=>{
 const html=render(Panel,{title:'Liquidity',meta:'PAPER',children:'Evidence'});
 assert.match(html,/aria-labelledby="[^"]+"/);assert.match(html,/<h2 id="[^"]+">Liquidity<\/h2>/);assert.match(html,/PAPER/);
});
test('shared empty and loading states describe missing evidence without zeros',()=>{
 assert.match(render(Empty,{children:'No observations yet.'}),/No observations yet/);
 const html=render(Loading,{title:'Connecting',children:'Waiting for a valid snapshot.'});assert.match(html,/role="status"/);assert.match(html,/aria-live="polite"/);assert.doesNotMatch(html,/\$0/);
});
test('error banners announce errors and ordinary notices use status semantics',()=>{
 assert.match(render(StatusBanner,{tone:'bad',children:'Unavailable'}),/role="alert"/);
 assert.match(render(StatusBanner,{children:'Historical'}),/role="status"/);
});
test('header never promotes disconnected prices or strategy status to current',()=>{
 const t=structuredClone(valid);t.emitted_at=new Date().toISOString();t.market.mid_price='12345.67';t.strategy.running=true;
 const html=header(t,'disconnected');
 assert.doesNotMatch(html,/12,345\.67/);assert.match(html,/LAST · RUNNING/);assert.match(html,/Last snapshot status/);assert.match(html,/Immediately activate manual kill switch/);
});
test('expired envelope with connected transport remains historical in header',()=>{
 const t=structuredClone(valid);t.emitted_at='2001-01-01T00:00:00Z';t.market.mid_price='12345.67';
 const html=header(t,'connected');
 assert.doesNotMatch(html,/12,345\.67/);assert.match(html,/LAST · RISK/);
});
test('unavailable header does not invent stopped strategy evidence',()=>{
 const html=header(null,'connecting');
 assert.match(html,/STRATEGY —/);assert.doesNotMatch(html,/disabled=""/);
});
test('kill latch remains disabled only once active, with immediate action label',()=>{
 const t=structuredClone(valid);t.emitted_at=new Date().toISOString();t.risk.kill_switch_active=true;
 const html=header(t,'connected');
 assert.match(html,/KILL ACTIVE/);assert.match(html,/aria-label="Immediately activate manual kill switch" disabled=""/);
 assert.doesNotMatch(header(t,'disconnected'),/aria-label="Immediately activate manual kill switch" disabled=""/);
});

test('every presentation mode links to all legacy routes and has distinct workspace links', () => {
 for (const mode of experienceModes) {
   const items = navigationGroups(mode).flatMap(group => group.items);
   const canonical = items.filter(item => !item.workspace).map(item => item.name);
   assert.deepEqual([...canonical].sort(), terminalPages.map(page => page.name).sort());
   const hrefs = items.map(item => item.workspace ? workspaceHref(item.workspace) : pageHref(item.name));
   assert.equal(new Set(hrefs).size, hrefs.length);
 }
 assert.deepEqual(navigationGroups('Starter')[0].items.map(item => item.label),
   ['Home', 'Market Explorer', 'Guided Research', 'Results', 'Help / Settings']);
 assert.equal(workspaceFromHash(workspaceHref('results')), 'results');
 assert.equal(pageFromHash(workspaceHref('results')), 'Simulation & Optimization');
 assert.equal(pageFromHash(workspaceHref('marketComparison')), 'Markets');
});
