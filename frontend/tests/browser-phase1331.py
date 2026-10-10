"""Read-only Phase 13.3.1 browser acceptance against local Uvicorn/Vite.
Fixtures are browser-only: never book economic events or submit venue orders.
Pass --backend-pid only for the dedicated DEMO/PAPER acceptance process.
"""
import argparse,asyncio,copy,json,os,signal,subprocess
from datetime import datetime,timezone
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[2]
WIDTHS=[1920,1440,1366,1024,768,390]
PAGES=['dashboard','markets','strategy','amm-settings','execution','risk','agents','vault','analytics','simulation','logs','settings']
def now():return datetime.now(timezone.utc).isoformat()
def fixture():
 t=json.loads((ROOT/'frontend/tests/fixtures/terminal-valid.json').read_text())
 t['process_id']='browser-fixture-process';t['session_id']='browser-fixture-session';t['sequence']=1;t['emitted_at']=now()
 t['vault']['updated_at']=now();t['vault']['stale']=False;t['vault']['error']=None
 base=copy.deepcopy(t['agents']['regime']);base['updated_at']=now()
 lq={**base,'agent':'LIQUIDITY_QUALITY','state':'THIN','metrics':{'thin_score':'0.8','imbalance_score':'0.4','instability_score':'0.2','concentration_score':'0.3','spread_bps':'2','bid_depth_base':'15','ask_depth_base':'12','book_span_bps':'30'}}
 pc={**base,'agent':'PERP_CROWDING','state':'LONG_CROWDED','metrics':{'long_crowding_score':'0.7','short_crowding_score':'0.1','basis_stress_score':'0.2','oi_change_ratio':None,'funding_rate_delta':None,'observation_count':1}}
 ml={**base,'agent':'PREDICTIVE_ADVERSE_SELECTION','state':'UNAVAILABLE','health':'INSUFFICIENT_DATA','mode':'SHADOW','affects_quotes':False,'spread_multiplier':'1','bid_size_multiplier':'1','ask_size_multiplier':'1','max_levels':None,'metrics':{'bid_adverse_probability':None,'ask_adverse_probability':None,'inference_confidence':None,'markout_horizon_seconds':'5','last_inference_time':None},'model_provenance':None,'feature_schema_version':'passive-adverse-v1','reasons':['Acceptance fixture: model inputs unavailable']}
 regime_fields=['direction','momentum_bps','realized_volatility','volatility_score','book_imbalance','trend_strength','funding_stress_score','basis_stress_score','book_pressure_score','inventory_stress_score']
 for output in [lq,pc,ml]:
  for k in regime_fields:output.pop(k,None)
 for key,value in [('liquidity_quality',lq),('perp_crowding',pc),('predictive_adverse_selection',ml)]:
  t['agents'][key]=value;t['agents']['supervisor'][key]=copy.deepcopy(value)
 t['agents']['regime']['health']='WARMING_UP';t['agents']['regime']['reasons']=['Acceptance fixture: history warming up']
 t['agents']['execution_quality']['health']='DEGRADED';t['agents']['execution_quality']['reasons']=['Acceptance fixture: insufficient execution support']
 t['agent_events']=[{'timestamp':now(),'agent':'REGIME','previous_state':'WARMING_UP','new_state':'NORMAL','reasons':['Acceptance fixture event reason'],'version':1}]
 return t
def ledger(t,entries=None):return {'mode':t['vault']['mode'],'market':t['vault']['market'],'ledger_version':t['vault']['ledger_version'],'ledger_fingerprint':t['vault']['ledger_fingerprint'],'order':'newest-first','retention_policy':'HALT_WHEN_FULL','entries':entries or []}
def entry(seq,event='TRADE_FILL',side='BID',source='PAPER_FILL'):
 return {'sequence':seq,'event_id':'fixture-economic-event-'+str(seq),'event_type':event,'timestamp':now(),'market':'ETH','side':side,'price':'3000.00000000000000001','size':'0.00000000000000001','cash_delta_quote':'-0.00000000000000000001','position_delta_base':'0.00000000000000001','fee_delta_quote':'0','funding_delta_quote':'0','realized_pnl_delta':'0','cash_balance_quote':'100000.00000000000000001','position_base':'0.00000000000000001','average_entry_price':'3000.00000000000000001','cumulative_realized_pnl':'0','cumulative_fees':'0','cumulative_funding':'0','source':source,'simulated':True,'event_fingerprint':'fixture-event-fingerprint-full','previous_ledger_fingerprint':'fixture-previous-fingerprint-full','ledger_fingerprint':'fixture-current-fingerprint-full'}
async def main(args):
 out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
 report={'layout_checks':[],'workflows':[],'page_errors':[],'console_errors':[],'fixture_notes':'Browser-only deterministic states; no backend economic writes or real TESTNET orders.'}
 replacement=None
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox'])
  context=await browser.new_context(timezone_id='America/Los_Angeles')
  page=await context.new_page()
  page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
  page.on('console',lambda m:report['console_errors'].append(m.text) if m.type=='error' else None)
  async def route(slug):
   await page.goto(args.url+'/#/'+slug)
   await page.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED')
   await page.wait_for_function('document.querySelector("#page-content")?.innerText.length > 30')
  for width in ([] if args.fixtures_only else WIDTHS):
   await page.set_viewport_size({'width':width,'height':900})
   for slug in PAGES:
    await route(slug)
    assert not await page.get_by_text('Terminal payload could not be rendered').count()
    geometry=await page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
    assert geometry['scroll']<=width+1,(width,slug,geometry)
    report['layout_checks'].append({'width':width,'page':slug,**geometry})
    if slug in ['agents','vault']:
     assert await page.locator('h1').is_visible()
     if slug=='agents':
      assert await page.locator('.researchAgent').count()==6
      control=page.locator('.researchAgent summary').first
      await control.focus();await page.keyboard.press('Enter')
      assert await control.evaluate('(s)=>s.parentElement.open')
      await page.keyboard.press('Enter');assert not await control.evaluate('(s)=>s.parentElement.open')
      await page.get_by_label('Agent event filter').select_option('REGIME')
      await page.wait_for_timeout(120)
      assert await page.get_by_label('Agent event filter').input_value()=='REGIME'
      await page.get_by_label('Agent event filter').select_option('')
      assert await page.get_by_text('ML SHADOW · OBSERVATIONAL ONLY',exact=False).is_visible()
     else:
      await page.get_by_text('No accounting events have been booked in this research session.',exact=True).wait_for()
      await page.wait_for_function("document.querySelectorAll('.historyChart canvas').length>=4")
      assert await page.locator('canvas').count()>=4
      provenance=page.get_by_text('Inspect full accounting identities',exact=True)
      await provenance.click();assert await provenance.evaluate('(s)=>s.parentElement.open')
     if width in [1440,390]:await page.screenshot(path=str(out/f'{slug}-{width}.png'),full_page=True)
  if not args.fixtures_only:report['workflows'].extend(['72 live page/viewport checks','agent keyboard expand/collapse at all six widths','live agent filter','live empty PAPER ledger','shared Vault history charts','full live provenance access'])
  if args.backend_pid and not args.fixtures_only:
   await route('vault')
   await page.get_by_text('Inspect full accounting identities',exact=True).click()
   old_identity=await page.locator('.vaultProvenance').inner_text()
   os.kill(args.backend_pid,signal.SIGTERM)
   await page.get_by_text('Historical financial observations',exact=False).wait_for(timeout=15000)
   assert not await page.get_by_text('No accounting events have been booked in this research session.',exact=True).count()
   await page.goto(args.url+'/#/agents')
   await page.get_by_text('Historical agent output',exact=False).wait_for()
   await page.get_by_text('Historical terminal events',exact=False).wait_for()
   env={**os.environ,'MARKET_DATA_MODE':'DEMO','EXECUTION_MODE':'PAPER','ENABLE_HYPERLIQUID_TESTNET_ORDERS':'false'}
   log=open(out/'restart-backend.txt','w')
   replacement=subprocess.Popen([args.python,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000'],cwd=ROOT/'backend',env=env,stdout=log,stderr=subprocess.STDOUT)
   await page.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED',timeout=25000)
   await route('vault');await page.get_by_text('No accounting events have been booked in this research session.',exact=True).wait_for()
   await page.get_by_text('Inspect full accounting identities',exact=True).click()
   assert old_identity!=await page.locator('.vaultProvenance').inner_text()
   report['workflows'].extend(['actual Uvicorn stop: historical Agents and Vault','actual backend restart: new provenance and fresh ledger; old ledger hidden'])
  if not args.fixtures_only:(out/'browser-live-results.json').write_text(json.dumps(report,indent=2))
  await context.close()
  # Separate browser context with deterministic terminal frames and read-only HTTP fixtures.
  ctx=await browser.new_context(timezone_id='America/Los_Angeles')
  fp=await ctx.new_page();fp.on('pageerror',lambda e:report['page_errors'].append(str(e)))
  t=fixture();state={'frame':t,'sequence':1,'ledger':ledger(t),'ledger_behavior':'ok','event_behavior':'ok','held':[], 'events':t['agent_events'],'ledger_calls':0,'event_calls':0}
  tasks=[]
  def socket(ws):
   async def publish():
    try:
     while True:
      f=copy.deepcopy(state['frame']);state['sequence']+=1;f['sequence']=state['sequence'];f['emitted_at']=now();f['vault']['updated_at']=now()
      ws.send(json.dumps(f));await asyncio.sleep(.4)
    except (asyncio.CancelledError,Exception):pass
   task=asyncio.create_task(publish());tasks.append(task)
   # Tasks are owned and cancelled explicitly at context shutdown.
  await ctx.route_web_socket('**/ws/terminal',socket)
  async def http(route):
   url=route.request.url
   if '/accounting/ledger' in url:
    state['ledger_calls']+=1
    if state['ledger_behavior']=='hold':state['held'].append((route,copy.deepcopy(state['ledger'])));return
    if state['ledger_behavior']=='error':await route.fulfill(status=503,json={'detail':'fixture ledger API unavailable'});return
    await route.fulfill(json=state['ledger']);return
   if '/agents/events' in url:
    state['event_calls']+=1
    if state['event_behavior']=='hold':state['held'].append((route,copy.deepcopy(state['events'])));return
    if state['event_behavior']=='error':await route.fulfill(status=503,json={'detail':'fixture events API unavailable'});return
    selected=state['events']
    from urllib.parse import urlparse,parse_qs
    agent=parse_qs(urlparse(url).query).get('agent',[None])[0]
    await route.fulfill(json=[e for e in selected if not agent or e['agent']==agent]);return
   if '/terminal/history' in url:
    await route.fulfill(json={'session_id':state['frame']['session_id'],'range':'session','retained_points':0,'retained_seconds':0,'max_points':3600,'max_age_seconds':3600,'points':[]});return
   if '/health' in url:
    await route.fulfill(json={'status':'ok','app':'HyperAMM','stale':False,'mode':'DEMO','simulated':True});return
   await route.continue_()
  await ctx.route('**/api/v1/**',http)
  async def fixture_route(slug):
   await fp.goto(args.url+'/#/'+slug)
   await fp.reload()
   await fp.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED')
   assert not await fp.get_by_text('Invalid terminal schema',exact=False).count()
  await fixture_route('agents')
  await fp.get_by_text('Acceptance fixture: history warming up',exact=True).wait_for()
  assert await fp.locator('.researchAgent').count()==6
  assert await fp.get_by_text('WARMING_UP',exact=True).count()>=1
  await fp.get_by_label('Agent event filter').select_option('REGIME')
  await fp.get_by_text('Acceptance fixture event reason',exact=True).wait_for()
  await fp.get_by_label('Agent event filter').select_option('SUPERVISOR')
  await fp.get_by_text('No retained agent events match this selection.',exact=True).wait_for()
  state['event_behavior']='error';await fp.get_by_role('button',name='Refresh retained events').click()
  await fp.get_by_text('Agent events could not be loaded:',exact=False).wait_for()
  state['event_behavior']='hold';await fp.get_by_label('Agent event filter').select_option('REGIME')
  await fp.get_by_text('Loading recent retained agent events…',exact=True).wait_for()
  for _ in range(50):
   if state['held']:break
   await asyncio.sleep(.05)
  assert state['held']
  state['frame']=copy.deepcopy(state['frame']);state['frame']['session_id']='fixture-events-new-session';state['frame']['agent_events']=[];state['events']=[];state['event_behavior']='ok'
  await asyncio.sleep(.9)
  for r,data in state['held']:
   try:await r.fulfill(json=data)
   except Exception:pass
  state['held']=[]
  await fp.get_by_text('No retained agent events match this selection.',exact=True).wait_for()
  assert not await fp.get_by_text('Acceptance fixture event reason',exact=True).count()
  report['workflows'].extend(['all six populated fixture agent cards','warmup/degraded/insufficient/model unavailable evidence','fixture agent event filtering/empty/API error/loading','stale in-flight agent event request rejected across session transition'])
  # Ledger entries are solely browser fixtures; no accounting mutation is performed.
  state['frame']['vault']['ledger_version']=3;state['frame']['accounting']['ledger_version']=3
  state['ledger']=ledger(state['frame'],[entry(3),entry(2,'FEE',None,'PAPER_CONFIG'),entry(1,'FUNDING',None,'PAPER_CONFIG')])
  await fixture_route('vault')
  await fp.get_by_text('View ledger entry 3',exact=True).wait_for()
  await fp.get_by_text('View ledger entry 3',exact=True).focus();await fp.keyboard.press('Enter')
  await fp.get_by_text('fixture-economic-event-3',exact=True).wait_for()
  assert await fp.get_by_text('fixture-previous-fingerprint-full',exact=True).first.is_visible()
  assert await fp.get_by_text('3000.00000000000000001',exact=True).count()>=1
  await fp.get_by_label('Ledger event type').select_option('FEE');assert await fp.get_by_text('View ledger entry 2',exact=True).is_visible();assert not await fp.get_by_text('View ledger entry 3',exact=True).count()
  await fp.get_by_label('Ledger side').select_option('ASK');await fp.get_by_text('No retained entries match these filters.',exact=True).wait_for()
  await fp.get_by_role('button',name='Clear ledger filters').click();await fp.get_by_label('Ledger source').select_option('PAPER_CONFIG');assert await fp.locator('.vaultLedger tbody tr').count()==2
  await fp.get_by_label('Ledger simulation').select_option('NON_SIMULATED');await fp.get_by_text('No retained entries match these filters.',exact=True).wait_for()
  await fp.get_by_role('button',name='Clear ledger filters').click()
  for width in WIDTHS:
   await fp.set_viewport_size({'width':width,'height':900})
   control=fp.get_by_text('View ledger entry 3',exact=True)
   if not await control.evaluate('(s)=>s.parentElement.open'):await control.click()
   assert await fp.evaluate('document.documentElement.scrollWidth <= innerWidth+1'),width
   if width in [1440,390]:await fp.screenshot(path=str(out/f'vault-ledger-fixture-{width}.png'),full_page=True)
  report['workflows'].extend(['fixture ledger keyboard details/full fingerprints/exact tiny decimals','ledger event/side/source/simulation/combined empty filters','populated ledger overflow and detail access at all six widths'])
  # API loading, failure and fingerprint mismatch.
  state['ledger_behavior']='error';await fixture_route('vault');await fp.get_by_text('Accounting ledger could not be loaded:',exact=False).wait_for()
  state['ledger_behavior']='ok';state['ledger']['ledger_version']=4
  await fp.get_by_role('button',name='Retry ledger observation').click();await fp.get_by_text('Ledger evidence changed during request;',exact=False).wait_for()
  state['ledger']['ledger_version']=3
  report['workflows'].append('ledger API error and version mismatch show explicit unavailable/error; no empty-success fallback')
  state['ledger_behavior']='hold';await fixture_route('vault');await fp.get_by_text('Loading / reconciling current ledger evidence…',exact=True).wait_for()
  for _ in range(50):
   if state['held']:break
   await asyncio.sleep(.05)
  assert state['held']
  state['frame']=copy.deepcopy(state['frame']);state['frame']['process_id']='fixture-restart-process';state['frame']['session_id']='fixture-restart-session';state['ledger_behavior']='ok';state['ledger']=ledger(state['frame'])
  await asyncio.sleep(.9)
  for r,data in state['held']:
   try:await r.fulfill(json=data)
   except Exception:pass
  state['held']=[]
  await fp.get_by_text('No accounting events have been booked in this research session.',exact=True).wait_for()
  assert not await fp.get_by_text('View ledger entry 3',exact=True).count()
  report['workflows'].append('old in-flight ledger with identical material provenance cannot populate replacement process/session')
  state['frame']['vault']['execution_accounting']['status']='DIVERGED';state['frame']['vault']['execution_accounting']['execution_accounting_consistent']=False;state['frame']['vault']['execution_accounting']['reason']='Acceptance fixture divergence';state['frame']['vault']['execution_accounting']['unaccounted_fill_count']=1
  await fp.get_by_text('DIVERGED',exact=True).wait_for();await fp.get_by_text('Acceptance fixture divergence',exact=True).wait_for()
  # TESTNET partial economics stays unavailable; no venue endpoint or signed order called.
  partial=copy.deepcopy(state['frame']);partial['session_id']='fixture-testnet-partial';partial['vault']['mode']='TESTNET';partial['strategy']['config']['execution_mode']='TESTNET';partial['vault']['simulated']=False;partial['vault']['accounting_complete']='PARTIAL'
  for key in ['initial_equity_quote','settled_capital_quote','available_capital_quote','reserved_capital_quote','realized_pnl_quote','net_pnl_quote','gross_pnl_quote','fees_quote','funding_quote','equity_quote']:partial['vault'][key]=None
  partial['accounting']['pnl']={k:None for k in partial['accounting']['pnl']}
  partial['vault']['execution_accounting'].update(status='UNAVAILABLE',execution_accounting_consistent=None,reason='Acceptance fixture: full TESTNET fill accounting unavailable')
  state['frame']=partial;state['ledger']=ledger(partial)
  await fp.get_by_text('TESTNET / PARTIAL',exact=True).wait_for()
  await fp.get_by_text('Complete authoritative TESTNET fill accounting is unavailable.',exact=True).wait_for()
  assert await fp.locator('.vaultSummary .metric strong').first.inner_text()=='Unavailable'
  assert await fp.locator('.vaultPnl .metric strong').first.inner_text()=='Unavailable'
  await fp.get_by_text('Not authoritative',exact=True).first.wait_for()
  report['workflows'].extend(['backend-reported DIVERGED consistency warning','TESTNET partial fixture missing equity/PnL and unavailable authoritative fill accounting'])
  for task in tasks:task.cancel()
  await ctx.close();await browser.close()
 if replacement:
  replacement.terminate();replacement.wait(timeout=15)
 assert not report['page_errors'],report['page_errors']
 if args.fixtures_only:
  live=json.loads((out/'browser-live-results.json').read_text())
  report['layout_checks']=live['layout_checks'];report['workflows']=live['workflows']+report['workflows'];report['console_errors']=live['console_errors']+report['console_errors'];report['page_errors']=live['page_errors']+report['page_errors']
 (out/'browser-results.json').write_text(json.dumps(report,indent=2))
 print(json.dumps({'layout_checks':len(report['layout_checks']),'workflows':len(report['workflows']),'page_errors':report['page_errors']}))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--url',default='http://127.0.0.1:5173');ap.add_argument('--chromium',default='/usr/bin/chromium');ap.add_argument('--python',default='/workspace/.hyperamm/venv/bin/python');ap.add_argument('--backend-pid',type=int);ap.add_argument('--output',required=True);ap.add_argument('--fixtures-only',action='store_true')
 asyncio.run(main(ap.parse_args()))
