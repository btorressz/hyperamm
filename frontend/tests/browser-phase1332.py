"""Local Phase 13.3.2 Chromium acceptance, isolated PAPER research only.
Browser fixtures never submit venue orders or modify backend economics.
Requires Playwright and system Chromium; no browser download is performed.
"""
import argparse, asyncio, copy, json, os, signal, subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[2]
SIZES=[(1920,1080),(1440,900),(1366,768),(1024,768),(768,900),(390,844)]
PAGES=['dashboard','markets','strategy','amm-settings','execution','risk','agents','vault','analytics','simulation','logs','settings']
def now(): return datetime.now(timezone.utc).isoformat()
async def main(args):
 out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
 report={'layout_checks':[],'workflows':[],'page_errors':[],'console_errors':[],'control_requests':[]}
 replacement=None
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox'])
  if not args.fixtures_only:
   ctx=await browser.new_context(timezone_id='America/Los_Angeles');page=await ctx.new_page()
   page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
   page.on('console',lambda m:report['console_errors'].append(m.text) if m.type=='error' else None)
   page.on('request',lambda r:report['control_requests'].append({'method':r.method,'url':r.url}) if r.method in ['POST','PUT','DELETE'] else None)
   async def route(slug):
    await page.goto(args.url+'/#/'+slug)
    await page.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED')
    await page.wait_for_function('document.querySelector("#page-content")?.innerText.length>30')
   async def terminal():return await page.evaluate("async()=> (await import('/src/stores/terminal.ts')).useTerminalStore.getState().terminal")
   await route('analytics');before=await terminal()
   assert before['market']['mode']=='DEMO' and before['strategy']['config']['execution_mode']=='PAPER'
   assert not before['strategy']['running'] and not before['diagnostics']['testnet_enabled']
   await page.get_by_role('button',name='SESSION',exact=True).wait_for()
   await page.wait_for_function("document.querySelectorAll('.analyticsPage .historyChart').length===4")
   hist=await page.evaluate("async()=> (await (await fetch('/api/v1/terminal/history?range=session&limit=600')).json())")
   if '1m' in hist['available_ranges']:
    await page.get_by_role('button',name='1M',exact=True).click()
    await page.wait_for_function("document.querySelector('.historyMetadata')?.innerText.includes('1M')")
    await page.reload();await page.get_by_role('button',name='1M',exact=True).wait_for()
    await page.wait_for_function("document.querySelector('.historyMetadata')?.innerText.includes('1M')")
    report['workflows'].append('live range query and persisted 1M preference')
   await page.get_by_role('button',name='SESSION',exact=True).click()
   await page.get_by_text('How to interpret execution metrics',exact=True).focus();await page.keyboard.press('Enter')
   assert await page.get_by_text('How to interpret execution metrics',exact=True).evaluate('(e)=>e.parentElement.open')
   await route('vault');await page.wait_for_function("document.querySelectorAll('.historyChart').length===4")
   report['workflows'].extend(['live Analytics four charts and keyboard explanations','live Vault shared chart regression'])
   await route('simulation')
   catalog=await page.evaluate("async()=> (await (await fetch('/api/v1/simulation/scenarios')).json())")
   (out/'scenario-catalog.json').write_text(json.dumps(catalog,indent=2))
   print('live simulation workflow',flush=True)
   await page.get_by_label('Scenario',exact=True).select_option('FLASH_MOVE')
   assert await page.get_by_text(next(s['description'] for s in catalog['scenarios'] if s['name']=='FLASH_MOVE'),exact=True).is_visible()
   await page.get_by_label('Frames',exact=True).fill('1');assert await page.get_by_role('button',name='Run Simulation',exact=True).is_disabled()
   await page.get_by_label('Frames',exact=True).fill('80')
   async with page.expect_response('**/api/v1/simulation/run') as response:
    await page.get_by_role('button',name='Run Simulation',exact=True).click()
   real_run=await (await response.value).json();(out/'live-simulation-result.json').write_text(json.dumps(real_run,indent=2))
   await page.get_by_role('heading',name='Completed run · FLASH_MOVE').wait_for()
   assert await page.locator('.simulationPage .historyChart').count()==6
   await page.get_by_text('Inspect full research fingerprints',exact=True).click()
   for key in ['run_fingerprint','dataset_fingerprint','strategy_fingerprint']:assert await page.get_by_text(real_run[key],exact=True).is_visible()
   await page.get_by_label('Scenario',exact=True).select_option('QUIET')
   assert await page.get_by_role('heading',name='Completed run · FLASH_MOVE').is_visible()
   await page.get_by_label('Frames',exact=True).fill('20')
   async with page.expect_response('**/api/v1/simulation/optimize',timeout=120000) as response:
    await page.get_by_role('button',name='Run Bounded Grid Search',exact=True).click()
   real_opt=await (await response.value).json();(out/'live-optimization-result.json').write_text(json.dumps(real_opt,indent=2))
   await page.get_by_label('Compare right',exact=True).wait_for();await page.get_by_label('Compare right',exact=True).select_option('2')
   await page.get_by_label('Compare left',exact=True).select_option('1')
   assert await page.get_by_role('heading',name=real_opt['ranked_candidates'][0]['label'],exact=True).count()>=1
   report['workflows'].extend(['actual FLASH_MOVE PAPER simulation: backend metrics, 80 trace frames and full provenance','captured run header survives scenario changes','actual Balanced grid: backend ordering and two-candidate comparison','frame input prevents invalid request; backend description displayed'])
   for width,height in SIZES:
    print('live viewport',width,flush=True)
    await page.set_viewport_size({'width':width,'height':height})
    # Preserve the completed real research outputs while changing viewport.
    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),('populated simulation',width)
    if width in [1440,390]:await page.screenshot(path=str(out/f'simulation-live-{width}.png'),full_page=True)
   after=await terminal()
   for key in ['strategy','risk']:
    if key=='strategy':assert after[key]['config']==before[key]['config'] and not after[key]['running']
    else:assert after[key]['kill_switch_active']==before[key]['kill_switch_active']
   assert after['vault']['ledger_version']==before['vault']['ledger_version']
   assert after['orders']==before['orders']
   report['workflows'].append('research/result inspection preserves active config, kill, ledger and orders')
   for width,height in SIZES:
    print('live viewport',width,flush=True)
    await page.set_viewport_size({'width':width,'height':height})
    for slug in PAGES:
     await route(slug)
     if slug in ['analytics','vault']:await page.wait_for_function("document.querySelectorAll('.historyChart').length===4")
     assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(slug,width)
     assert not await page.get_by_text('Terminal payload could not be rendered',exact=False).count()
     report['layout_checks'].append({'page':slug,'width':width,'height':height})
     if slug=='analytics' and width in [1440,390]:await page.screenshot(path=str(out/f'analytics-live-{width}.png'),full_page=True)
   if args.backend_pid:
    await page.set_viewport_size({'width':1440,'height':900});await route('analytics')
    old=(await terminal())['session_id'];os.kill(args.backend_pid,signal.SIGTERM)
    await page.get_by_text('Historical analytics · last accepted terminal snapshot.',exact=False).wait_for(timeout=15000)
    assert await page.get_by_text('Historical session charts',exact=False).is_visible()
    env={**os.environ,'MARKET_DATA_MODE':'DEMO','EXECUTION_MODE':'PAPER','ENABLE_HYPERLIQUID_TESTNET_ORDERS':'false'}
    replacement=subprocess.Popen([args.python,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000'],cwd=ROOT/'backend',env=env,stdout=open(out/'restart-backend.txt','w'),stderr=subprocess.STDOUT)
    await page.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED',timeout=30000)
    await page.wait_for_function("document.querySelectorAll('.analyticsPage .historyChart').length===4")
    fresh=await terminal();assert fresh['session_id']!=old
    await page.get_by_text('Inspect retention and session identity',exact=True).click()
    assert old not in await page.locator('.historyMetadata').inner_text()
    report['workflows'].append('actual backend stop/restart: historical chart freeze and new-session reset')
   await ctx.close()
   print('live checks passed; fixture workflows',flush=True)
   (out/'browser-live-results.json').write_text(json.dumps(report,indent=2))
  else:
   report=json.loads((out/'browser-live-results.json').read_text())
   real_run=json.loads((out/'live-simulation-result.json').read_text())
   real_opt=json.loads((out/'live-optimization-result.json').read_text())
   catalog=json.loads((out/'scenario-catalog.json').read_text())
  # Browser-only edge cases with schema-valid streaming terminal and HTTP fixtures.
  fx=await browser.new_context(timezone_id='America/Los_Angeles');fp=await fx.new_page();fp.on('pageerror',lambda e:report['page_errors'].append(str(e)))
  t=json.loads((ROOT/'frontend/tests/fixtures/terminal-valid.json').read_text());t['process_id']='phase1332-fixture-process';t['session_id']='phase1332-fixture-session'
  state={'terminal':t,'sequence':0,'history_behavior':'ok','held':[],'run_behavior':'ok','opt_behavior':'ok','run_calls':0,'opt_calls':0,'requests':[]}
  tasks=[]
  def socket(ws):
   async def publish():
    try:
     while True:
      if state.get('paused'):
       await asyncio.sleep(.1);continue
      f=copy.deepcopy(state['terminal']);state['sequence']+=1;f['sequence']=state['sequence'];f['emitted_at']=now();f['vault']['updated_at']=now();ws.send(json.dumps(f));await asyncio.sleep(.2)
    except Exception:pass
   task=asyncio.create_task(publish());tasks.append(task)
  await fx.route_web_socket('**/ws/terminal',socket)
  def history_fixture(range,limit):
   base=datetime.now(timezone.utc)-timedelta(seconds=300)
   points=[{'sequence':i+1,'timestamp':(base+timedelta(seconds=i*60)).isoformat(),'equity':None if i==2 else str(100+i),'peak_equity':str(100+i),'net_pnl':str(i-2),'position_base':str((i-2)/100),'drawdown_pct':'0.05','capital_utilization':'0.25','risk_state':'HALT' if i==3 else 'NORMAL','agent_regime':'QUIET','simulated':True,'execution_mode':'PAPER'} for i in range_fn(6)]
   seconds={'session':None,'1m':60,'5m':300,'15m':900,'1h':3600}[range]
   if seconds is not None:points=[p for p in points if datetime.fromisoformat(p['timestamp'])>=base+timedelta(seconds=300-seconds)]
   return {'session_id':state['terminal']['session_id'],'range':range,'max_points':3600,'query_max':1000,'retained_points':6,'retained_seconds':300,'available_ranges':['session','1m','5m'],'oldest_at':base.isoformat(),'latest_at':(base+timedelta(seconds=300)).isoformat(),'points':points[-limit:]}
  range_fn=range
  async def fixture_api(route):
   url=route.request.url;state['requests'].append({'method':route.request.method,'url':url});path=urlparse(url).path
   if path.endswith('/simulation/scenarios'):return await route.fulfill(json=catalog)
   if path.endswith('/terminal/history'):
    q=parse_qs(urlparse(url).query);data=history_fixture(q.get('range',['session'])[0],int(q.get('limit',['600'])[0]))
    if state['history_behavior']=='hold':
     event=asyncio.Event();state['held'].append((event,data));await event.wait()
    if state['history_behavior']=='error':return await route.fulfill(status=503,json={'detail':'fixture history unavailable'})
    try:return await route.fulfill(json=data)
    except Exception:return
   if path.endswith('/simulation/run') or path.endswith('/simulation/optimize'):
    kind='run' if path.endswith('/run') else 'opt';state[kind+'_calls']+=1;behavior=state[kind+'_behavior']
    if behavior=='hold':
     event=asyncio.Event();state['research_held']=event;await event.wait()
    if isinstance(behavior,int):return await route.fulfill(status=behavior,json={'detail':'fixture request error'})
    if behavior=='network':return await route.abort('failed')
    data=copy.deepcopy(real_run if kind=='run' else real_opt)
    if kind=='run':
     body=route.request.post_data_json;data['scenario']=body['scenario'];data['run_fingerprint']='fixture-run-full';data['trace']=data['trace'][:3]
     for i,point in enumerate(data['trace']):point['sequence']=i+1;point['timestamp']='2026-01-01T00:00:00Z'
     data['trace'][1]['equity']=None;data['trace'][1]['inventory_base']='NaN';data['trace'][2]['timestamp']='invalid';data['metrics']['mean_mature_markout_bps']=None
    else:
     data['baseline']['validation_score']=None;data['baseline']['score_delta']=None;data['rejected_candidates']=[{'reason':'fixture bounded field rejected','strategy_updates':{'levels_per_side':0}}]
    return await route.fulfill(json=data)
   return await route.continue_()
  await fx.route('**/api/v1/**',fixture_api)
  async def fr(slug):await fp.goto(args.url+'/#/'+slug);await fp.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED')
  await fr('analytics');await fp.wait_for_function("document.querySelectorAll('.analyticsPage .historyChart').length===4")
  assert await fp.get_by_role('button',name='15M',exact=True).is_disabled()
  assert await fp.get_by_role('button',name='1H',exact=True).is_disabled()
  await fp.get_by_text('Inspect chart observations',exact=True).nth(3).click()
  dd=fp.get_by_role('region',name='Drawdown & capital utilization',exact=True)
  assert '5%' in await dd.inner_text() and '25%' in await dd.inner_text()
  await fp.get_by_text('Inspect chart observations',exact=True).nth(0).click()
  assert 'Unavailable' in await fp.get_by_role('region',name='Equity & high-water mark',exact=True).inner_text()
  assert '5 observations' in await fp.get_by_label('Risk states',exact=True).inner_text()
  await fp.get_by_role('button',name='1M',exact=True).click();await fp.wait_for_function("document.querySelector('.historyMetadata')?.innerText.includes('2 returned samples')")
  await fp.evaluate("async()=> (await import('/src/stores/display.ts')).useDisplayStore.getState().setHistorySize(100)")
  await fp.wait_for_timeout(300);assert any('limit=100' in r['url'] for r in state['requests'])
  await fp.get_by_role('button',name='SESSION',exact=True).click()
  await fp.evaluate("async()=> (await import('/src/stores/display.ts')).useDisplayStore.getState().setDefaultRange('15m')")
  await fp.get_by_text('Saved preference 15M',exact=False).wait_for()
  assert await fp.get_by_role('button',name='SESSION',exact=True).get_attribute('aria-pressed')=='true'
  await fp.evaluate("async()=> (await import('/src/stores/display.ts')).useDisplayStore.getState().setDefaultRange('session')")
  for width,height in SIZES:
   await fp.set_viewport_size({'width':width,'height':height});assert await fp.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
   if width in [1440,390]:await fp.screenshot(path=str(out/f'analytics-fixture-{width}.png'),full_page=True)
  report['workflows'].extend(['fixture retention disabled ranges, saved unavailable preference and size-bound queries','fixture chart gaps, signed base and percent axes/data; actual sample-count distribution','fixture Analytics all six viewports'])
  # A suspended old-session HTTP response must never reappear in the replacement chart.
  state['history_behavior']='hold';await fp.evaluate("async()=> (await import('/src/stores/display.ts')).useDisplayStore.getState().setHistorySize(101)")
  for _ in range_fn(50):
   if state['held']:break
   await fp.wait_for_timeout(50)
  assert state['held'];old_session=state['terminal']['session_id'];state['terminal']['process_id']='replacement-fixture-process';state['terminal']['session_id']='replacement-fixture-session';state['history_behavior']='ok'
  await fp.wait_for_function("document.querySelectorAll('.analyticsPage .historyChart').length===4")
  for event,data in state['held']:event.set()
  await fp.wait_for_timeout(400);await fp.get_by_text('Inspect retention and session identity',exact=True).click()
  assert old_session not in await fp.locator('.historyMetadata').inner_text()
  report['workflows'].append('fixture old in-flight history after process/session replacement rejected')
  state['history_behavior']='error';state['terminal']['session_id']='history-error-fixture-session'
  await fp.get_by_role('alert').filter(has_text='fixture history unavailable').wait_for()
  assert not await fp.get_by_text('Loading session observations…',exact=True).count()
  state['history_behavior']='ok';await fp.get_by_role('button',name='Retry history',exact=True).click()
  await fp.wait_for_function("document.querySelectorAll('.analyticsPage .historyChart').length===4")
  state['paused']=True
  await fp.evaluate("async()=> (await import('/src/stores/terminal.ts')).useTerminalStore.getState().setWsState('disconnected')")
  await fp.get_by_text('Historical session charts',exact=False).wait_for()
  assert await fp.locator('.analyticsPage .historyChart').count()==4
  state['paused']=False
  await fp.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED')
  report['workflows'].append('fixture history error/retry and disconnected retained chart evidence')

  await fr('simulation');await fp.set_viewport_size({'width':1440,'height':900})
  await fp.get_by_label('Frames',exact=True).fill('2.5');assert await fp.get_by_role('button',name='Run Simulation',exact=True).is_disabled()
  await fp.get_by_label('Frames',exact=True).fill('120');state['run_behavior']='hold'
  await fp.get_by_role('button',name='Run Simulation',exact=True).click()
  await fp.get_by_text('Running QUIET',exact=False).wait_for()
  assert await fp.get_by_role('button',name='Running…',exact=True).is_disabled()
  assert await fp.get_by_role('button',name='Run Bounded Grid Search',exact=True).is_disabled()
  await fp.get_by_label('Scenario',exact=True).select_option('TREND_UP');state['research_held'].set()
  await fp.get_by_role('heading',name='Completed run · QUIET').wait_for();assert state['run_calls']==1
  assert await fp.locator('.simulationPage .historyChart').count()==6
  await fp.get_by_text('Inspect chart observations',exact=True).first.click()
  table=fp.get_by_role('region',name='Simulated equity',exact=True)
  assert await table.locator('tbody tr').count()==3 and 'Unavailable' in await table.inner_text()
  state['opt_behavior']='ok';await fp.get_by_label('Optimization preset',exact=True).select_option('Inventory')
  await fp.get_by_role('button',name='Run Bounded Grid Search',exact=True).click();await fp.get_by_label('Compare left',exact=True).wait_for()
  assert await fp.get_by_role('heading',name='Completed parameter study · Inventory',exact=True).is_visible()
  await fp.get_by_label('Compare right',exact=True).select_option('0')
  assert await fp.get_by_text('Unavailable',exact=True).count()>0
  await fp.get_by_text('Inspect rejected candidate 1',exact=True).click();assert await fp.get_by_text('"fixture bounded field rejected"',exact=True).is_visible()
  await fp.get_by_label('Compare right',exact=True).select_option('2')
  for width,height in SIZES:
   await fp.set_viewport_size({'width':width,'height':height});assert await fp.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
   if width in [1440,390]:await fp.screenshot(path=str(out/f'simulation-fixture-{width}.png'),full_page=True)
  report['workflows'].extend(['fixture busy state: single admission and changing controls never relabel captured response','fixture trace same-second frames, missing/nonfinite metrics and invalid timestamps','fixture Inventory preset, baseline/candidate selectors, null validation and rejection details','fixture populated Simulation all six viewports'])
  for status in [422,429,503,500,'network']:
   state['run_behavior']=status;await fp.get_by_role('button',name='Run Simulation',exact=True).click()
   expected={422:'Review the scenario',429:'Research capacity is busy',503:'coordination is restored',500:'backend diagnostics','network':'Network request failed'}[status]
   await fp.get_by_role('alert').filter(has_text=expected).wait_for()
   report['workflows'].append('fixture research error '+str(status)+' actionable')
  # Navigate away while research is pending, then back before the old response completes.
  state['run_behavior']='hold';await fp.get_by_role('button',name='Run Simulation',exact=True).click();await fp.get_by_text('Running TREND_UP',exact=False).wait_for();event=state['research_held']
  await fr('analytics');await fr('simulation');event.set();await fp.wait_for_timeout(300)
  assert not await fp.get_by_role('heading',name='Completed run · TREND_UP').count()
  report['workflows'].append('fixture unmounted research completion cannot seed replacement page')
  forbidden=[r for r in state['requests'] if r['method'] in ['POST','PUT','DELETE'] and '/simulation/' not in r['url']]
  assert not forbidden
  assert not [r for r in report['control_requests'] if '/simulation/' not in r['url']]
  report['workflows'].append('zero non-research mutation requests across browser acceptance')
  await fp.set_viewport_size({'width':1440,'height':900})
  await fp.evaluate("""async()=>{
   const React=(await import('/node_modules/.vite/deps/react.js')).default;
   const {createRoot}=(await import('/node_modules/.vite/deps/react-dom_client.js')).default;
   const {HistoryChart}=await import('/src/components/HistoryChart.tsx');
   const Native=window.ResizeObserver;window.chartObserverCount=0;
   window.ResizeObserver=class extends Native{constructor(cb){super(cb);this.counted=true;window.chartObserverCount++;}disconnect(){super.disconnect();if(this.counted){window.chartObserverCount--;this.counted=false;}}};
   const host=document.createElement('div');host.id='chart-lifecycle-acceptance';host.style.width='420px';document.body.append(host);
   const root=createRoot(host),points=[{sequence:1,timestamp:'2026-01-01T00:00:00Z',equity:'100',drawdown_pct:'0.05'},{sequence:2,timestamp:'2026-01-01T00:00:01Z',equity:null,drawdown_pct:null},{sequence:3,timestamp:'2026-01-01T00:00:02Z',equity:'102',drawdown_pct:'0.1'}];
   window.chartAcceptance={host,root,Native,render:(lines,height=220)=>root.render(React.createElement(HistoryChart,{points,lines,height}))};
   window.chartAcceptance.render([{key:'equity',label:'Lifecycle equity',unit:'quote',color:'#4cd4a1'}]);
  }""")
  await fp.wait_for_function("document.querySelector('#chart-lifecycle-acceptance .historyChart canvas')!==null && window.chartObserverCount>=1")
  await fp.evaluate("window.chartAcceptance.render([{key:'drawdown_pct',label:'Lifecycle drawdown',percent:true,color:'#f0788a'}],260)")
  await fp.wait_for_function("document.querySelector('#chart-lifecycle-acceptance').innerText.includes('Lifecycle drawdown')")
  assert 'Lifecycle equity' not in await fp.locator('#chart-lifecycle-acceptance').inner_text()
  await fp.evaluate("window.chartAcceptance.host.style.width='300px'")
  await fp.wait_for_function("document.querySelector('#chart-lifecycle-acceptance .historyChart').getBoundingClientRect().width<=300")
  await fp.get_by_role('button',name='Reset Lifecycle drawdown chart view',exact=True).focus();await fp.keyboard.press('Enter')
  await fp.evaluate("()=>{window.chartAcceptance.root.unmount();window.chartAcceptance.host.remove();window.ResizeObserver=window.chartAcceptance.Native;}")
  assert await fp.evaluate('window.chartObserverCount')==0
  report['workflows'].append('real chart mount: config replacement, height/width resize, keyboard reset and observer cleanup')

  for task in tasks:task.cancel()
  await fx.close();await browser.close()
 if replacement:
  replacement.terminate();replacement.wait(timeout=15)
 assert not report['page_errors'],report['page_errors']
 (out/'browser-results.json').write_text(json.dumps(report,indent=2))
 print(json.dumps({'layout_checks':len(report['layout_checks']),'workflows':len(report['workflows']),'page_errors':report['page_errors']},indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--url',default='http://127.0.0.1:5173');ap.add_argument('--output',required=True);ap.add_argument('--chromium',default='/usr/bin/chromium');ap.add_argument('--backend-pid',type=int);ap.add_argument('--fixtures-only',action='store_true');ap.add_argument('--python',default='/workspace/.hyperamm/venv/bin/python');asyncio.run(main(ap.parse_args()))
