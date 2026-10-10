"""Local DEMO/PAPER acceptance; deterministic fixtures never create venue orders."""
import argparse, asyncio, copy, json, os, signal, subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright
ROOT = Path(__file__).resolve().parents[2]
SIZES = [(1920,1080),(1440,900),(1366,768),(1024,768),(768,900),(390,844)]
PAGES = ['dashboard','markets','strategy','amm-settings','execution','risk','agents','vault','analytics','simulation','logs','settings']
def now(): return datetime.now(timezone.utc).isoformat()
def event(index, **patch):
 return dict(event_id='fixture-event-'+str(index),timestamp='2026-01-01T00:00:00Z',category='RISK',previous_state='NORMAL',state='WIDEN',message='Fixture message '+str(index),reference='fixture-reference-'+str(index),version=index,simulated=True,**patch) if not patch else {**event(index),**patch}
async def main(args):
 out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
 report={'layout_checks':[],'workflows':[],'page_errors':[],'mutations':[],'fixtures':'Browser-only records; no real venue activity or credentials.'}
 def passed(name): report['workflows'].append(name); print(name,flush=True)
 replacement=None
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox'])
  if not args.fixtures_only:
   ctx=await browser.new_context(timezone_id='America/Los_Angeles',accept_downloads=True)
   page=await ctx.new_page();page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
   page.on('request',lambda r:report['mutations'].append({'method':r.method,'url':r.url}) if r.method in ['POST','PUT','PATCH','DELETE'] else None)
   async def route(slug):
    await page.goto(args.url+'/#/'+slug)
    await page.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED')
    await page.wait_for_function('document.querySelector("#page-content")?.innerText.length>30')
   async def terminal():return await page.evaluate("async()=> (await import('/src/stores/terminal.ts')).useTerminalStore.getState().terminal")
   await route('logs');await page.get_by_role('region',name='Loaded event timeline').wait_for()
   before=await terminal();assert before['market']['mode']=='DEMO' and before['strategy']['config']['execution_mode']=='PAPER'
   assert not before['diagnostics']['testnet_enabled'] and not before['strategy']['running']
   print('live Logs',flush=True)
   await page.get_by_role('group',name='Event category').get_by_role('button',name='RISK',exact=True).click()
   await page.get_by_role('region',name='Loaded event timeline').wait_for()
   assert await page.get_by_role('button',name='RISK',exact=True).get_attribute('aria-pressed')=='true'
   await page.get_by_role('button',name='Reset filters',exact=True).click()
   await page.get_by_label('Requested event limit',exact=True).select_option('500')
   await page.get_by_label('Search loaded events',exact=True).fill('no-such-message-1333')
   await page.get_by_text('No loaded events match this search.',exact=False).wait_for()
   await page.get_by_role('button',name='Clear search',exact=True).click()
   await page.get_by_label('Display order',exact=True).select_option('oldest-first')
   controls=page.get_by_role('button',name='Inspect event',exact=False)
   await controls.first.wait_for();await controls.first.focus();await page.keyboard.press('Enter')
   assert await page.get_by_text('Full message',exact=True).count()==1
   async with page.expect_download() as dl:await page.get_by_role('button',name='Export loaded events (bounded session evidence)',exact=True).click()
   download=await dl.value;export=json.loads(Path(await download.path()).read_text())
   assert export['requested_limit']==500 and export['display_order']=='oldest-first'
   assert export['loaded_event_count']==export['exported_event_count']<=500
   assert export['client_observed_identity']['session_id']==before['session_id']
   assert set(export['events'][0])=={'event_id','timestamp','category','previous_state','state','message','reference','version','simulated'}
   passed('live Logs category/search/reset/order/keyboard details and bounded JSON export')
   await page.set_viewport_size({'width':1440,'height':900});await page.screenshot(path=str(out/'logs-live-1440.png'))
   await route('settings')
   await page.get_by_label('Layout density',exact=True).select_option('dense')
   await page.get_by_label('Sidebar layout',exact=True).select_option('collapsed')
   await page.get_by_label('Default chart range',exact=True).select_option('1h')
   await page.get_by_label('History view size',exact=True).select_option('100')
   await page.get_by_text('Saved locally in this browser.',exact=False).wait_for()
   await page.reload();await page.get_by_label('Layout density',exact=True).wait_for()
   assert await page.get_by_label('Layout density',exact=True).input_value()=='dense'
   assert await page.get_by_label('Sidebar layout',exact=True).input_value()=='collapsed'
   assert await page.get_by_label('Default chart range',exact=True).input_value()=='1h'
   assert await page.get_by_label('History view size',exact=True).input_value()=='100'
   await page.get_by_role('button',name='Expand navigation',exact=True).wait_for()
   await route('analytics');await page.wait_for_function("document.querySelectorAll('.historyChart').length===4")
   await page.get_by_text('Saved preference 1H',exact=False).wait_for()
   assert await page.get_by_role('button',name='SESSION',exact=True).get_attribute('aria-pressed')=='true'
   assert await page.evaluate("JSON.parse(localStorage.getItem('hyperamm-display-v1')).state.defaultRange")=='1h'
   passed('live Settings persistence survives refresh; unavailable saved range remains 1H while Analytics shows SESSION')
   await route('settings');await page.get_by_role('button',name='Reset display preferences',exact=True).click()
   await page.get_by_role('group',name='Confirm display preference reset').wait_for()
   await page.get_by_role('button',name='Cancel reset',exact=True).click()
   assert await page.get_by_label('Layout density',exact=True).input_value()=='dense'
   await page.get_by_role('button',name='Reset display preferences',exact=True).click()
   await page.get_by_role('button',name='Confirm display reset',exact=True).focus();await page.keyboard.press('Enter')
   await page.reload();await page.get_by_label('Layout density',exact=True).wait_for()
   assert await page.evaluate("JSON.parse(localStorage.getItem('hyperamm-display-v1')).state")=={'dense':False,'sidebarCollapsed':False,'historySize':600,'defaultRange':'session'}
   after=await terminal()
   assert after['strategy']['config']==before['strategy']['config'] and not after['strategy']['running']
   assert after['risk']['kill_switch_active']==before['risk']['kill_switch_active']
   assert after['vault']['ledger_version']==before['vault']['ledger_version'] and after['orders']==before['orders']
   passed('live reset confirmation/cancel/keyboard/defaults/refresh preserve strategy, kill, ledger and orders')
   await page.screenshot(path=str(out/'settings-live-1440.png'),full_page=True)
   await route('vault');await page.wait_for_function("document.querySelectorAll('.historyChart').length===4")
   await route('analytics');await page.wait_for_function("document.querySelectorAll('.historyChart').length===4")
   passed('live reset leaves Vault, Analytics and Sidebar functional')
   for first,second in [('agents','logs'),('vault','analytics'),('analytics','settings'),('settings','analytics'),('simulation','logs'),('logs','agents')]:
    await route(first);await page.get_by_role('link',name={'agents':'Supervisory Agents','analytics':'Analytics','settings':'Settings','logs':'Logs'}[second],exact=True).click()
    assert page.url.endswith('/'+second)
   passed('all six specified cross-page transitions preserve accepted terminal identity')
   for width,height in SIZES:
    await page.set_viewport_size({'width':width,'height':height})
    for slug in PAGES:
     await route(slug)
     if slug in ['vault','analytics']:await page.wait_for_function("document.querySelectorAll('.historyChart').length===4")
     assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(slug,width)
     assert not await page.get_by_text('Terminal payload could not be rendered',exact=False).count()
     report['layout_checks'].append({'route':slug,'width':width,'height':height})
    print('12 routes at '+str(width),flush=True)
   await page.get_by_role('button',name='Open navigation',exact=True).click()
   await page.get_by_role('dialog',name='Terminal navigation').wait_for()
   await page.keyboard.press('Escape');assert not await page.get_by_role('dialog',name='Terminal navigation').count()
   passed('72 live route/viewport checks; mobile drawer keyboard dismissal')
   if args.backend_pid:
    await page.set_viewport_size({'width':1440,'height':900});await route('logs')
    await page.get_by_role('region',name='Loaded event timeline').wait_for()
    old=(await terminal())['session_id'];os.kill(args.backend_pid,signal.SIGTERM)
    await page.get_by_text('Historical event evidence',exact=False).wait_for(timeout=15000)
    assert await page.get_by_role('region',name='Loaded event timeline').count()==1
    await page.get_by_role('link',name='Settings',exact=True).click()
    await page.get_by_text('Historical or unavailable backend evidence',exact=False).wait_for()
    assert not await page.locator('.settingsPage .badge.good').count()
    await page.get_by_label('Layout density',exact=True).select_option('dense')
    env={**os.environ,'MARKET_DATA_MODE':'DEMO','EXECUTION_MODE':'PAPER','ENABLE_HYPERLIQUID_TESTNET_ORDERS':'false'}
    replacement=subprocess.Popen([args.python,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000'],cwd=ROOT/'backend',env=env,stdout=open(out/'restart-backend.txt','w'),stderr=subprocess.STDOUT)
    await page.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED',timeout=30000)
    assert (await terminal())['session_id']!=old
    await route('logs');await page.get_by_role('region',name='Loaded event timeline').wait_for()
    await page.get_by_text('Inspect event session identity and scope',exact=True).click()
    assert old not in await page.locator('.logsPage .operationsDetails').inner_text()
    passed('actual backend stop/restart: historical Logs freeze, historical health, editable preferences, new-session isolation')
   (out/'browser-live-results.json').write_text(json.dumps(report,indent=2))
   await ctx.close()
  else: report=json.loads((out/'browser-live-results.json').read_text())
  # Schema-valid streaming terminal with isolated HTTP event fixtures.
  fx=await browser.new_context(timezone_id='America/Los_Angeles',accept_downloads=True)
  fp=await fx.new_page();fp.on('pageerror',lambda e:report['page_errors'].append(str(e)))
  t=json.loads((ROOT/'frontend/tests/fixtures/terminal-valid.json').read_text())
  t['process_id']='phase1333-fixture-process';t['session_id']='phase1333-fixture-session'
  reference_fixture=copy.deepcopy(t['references']);consensus_fixture=copy.deepcopy(t['reference_consensus'])
  state={'terminal':t,'sequence':0,'events':[event(1,message='Case-sensitive NEEDLE '+'long message '*80),event(2,category='SYSTEM',simulated=False),event(3,reference=None,version=None,previous_state=None,state=None)],'behavior':'ok','held':[],'requests':[],'paused':False}
  tasks=[]
  def socket(ws):
   async def publish():
    try:
     while True:
      if not state['paused']:
       f=copy.deepcopy(state['terminal']);state['sequence']+=1;f['sequence']=state['sequence'];f['emitted_at']=now();ws.send(json.dumps(f))
      await asyncio.sleep(.2)
    except Exception:pass
   tasks.append(asyncio.create_task(publish()))
  await fx.route_web_socket('**/ws/terminal',socket)
  async def api(route):
   url=urlparse(route.request.url);state['requests'].append({'method':route.request.method,'url':route.request.url})
   if url.path.endswith('/health'):return await route.fulfill(json={'status':'ok'})
   if url.path.endswith('/terminal/events'):
    query=parse_qs(url.query);category=query.get('category',[None])[0];limit=int(query['limit'][0])
    data={'session_id':state['terminal']['session_id'],'order':'newest-first','max_events':500,'events':copy.deepcopy([e for e in state['events'] if not category or e['category']==category][:limit])}
    behavior=state['behavior']
    if behavior=='hold':
     release=asyncio.Event();state['held'].append((release,data));await release.wait()
    if behavior=='error':return await route.fulfill(status=503,json={'detail':'Fixture events unavailable'})
    if behavior=='malformed':data['events'][0]['reference']=123
    if behavior=='wrong-session':data['session_id']='retired-session'
    try:return await route.fulfill(json=data)
    except Exception:return
   return await route.continue_()
  await fx.route('**/api/v1/**',api)
  async def fr(slug):
   await fp.goto(args.url+'/#/'+slug);await fp.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED')
  async def logs_ready():await fp.get_by_role('region',name='Loaded event timeline').wait_for()
  await fr('logs');await logs_ready()
  await fp.get_by_label('Search loaded events',exact=True).fill('  needle ')
  await fp.get_by_text('1 matching events out of 3 loaded events.',exact=False).wait_for()
  assert not await fp.get_by_role('button',name='Inspect event fixture-event-2',exact=True).count()
  await fp.get_by_role('button',name='Inspect event fixture-event-1',exact=True).focus();await fp.keyboard.press('Enter')
  assert 'long message '*80 in await fp.locator('.logsPage .operationsDetails').last.inner_text()
  async with fp.expect_download() as dl:await fp.get_by_role('button',name='Export loaded events (bounded session evidence)',exact=True).click()
  exported=json.loads(Path(await (await dl.value).path()).read_text())
  assert exported['loaded_event_count']==3 and exported['exported_event_count']==1
  assert exported['events'][0]==state['events'][0] and 'search' not in exported
  assert not await fp.evaluate("localStorage.getItem('needle')")
  await fp.get_by_role('button',name='Clear search',exact=True).click()
  await fp.get_by_label('Search loaded events',exact=True).fill('REFERENCE-2')
  await fp.get_by_role('button',name='Inspect event fixture-event-2',exact=True).wait_for()
  await fp.get_by_role('button',name='Reset filters',exact=True).click()
  await fp.get_by_label('Display order',exact=True).select_option('oldest-first')
  assert [text.split(' event ')[1] for text in await fp.locator('.eventDetailsToggle').all_text_contents()]==['fixture-event-1','fixture-event-2','fixture-event-3']
  passed('fixture message/reference case-insensitive trimmed search, reset, stable equal-time ordering, full details and exact filtered export')
  await fp.get_by_role('button',name='Inspect event fixture-event-3',exact=True).click()
  assert 'Null (not reported)' in await fp.locator('.logsPage .operationsDetails').last.inner_text()
  assert 'No state transition reported' in await fp.locator('.eventTable').inner_text()
  for width,height in SIZES:
   await fp.set_viewport_size({'width':width,'height':height});assert await fp.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
   if width==390:await fp.locator('.logsPage').screenshot(path=str(out/'logs-fixture-390.png'))
  passed('fixture null fields, simulated versus unflagged records, long messages and narrow scrollable tables at six viewports')
  state['events']=[event(i) for i in range(500)]
  await fp.get_by_label('Requested event limit',exact=True).select_option('500')
  await fp.get_by_text('500 matching events out of 500 loaded events.',exact=False).wait_for()
  assert await fp.locator('.eventDetailsToggle').count()==500
  assert await fp.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
  passed('fixture full 500-event bound with loaded/retained counts and no unbounded pagination')
  state['events']=[]
  await fp.get_by_role('button',name='SYSTEM',exact=True).click();await fp.get_by_text('No events returned for this session and category.',exact=True).wait_for()
  state['events']=[event(1)];state['behavior']='error';await fp.get_by_role('button',name='RISK',exact=True).click()
  await fp.get_by_role('alert').filter(has_text='Fixture events unavailable').wait_for()
  assert not await fp.get_by_text('No events returned for this session and category.',exact=True).count()
  state['behavior']='malformed';await fp.get_by_role('button',name='Retry events',exact=True).click()
  await fp.get_by_role('alert').filter(has_text='incompatible').wait_for()
  state['behavior']='wrong-session';await fp.get_by_role('button',name='Retry events',exact=True).click()
  await fp.get_by_role('alert').filter(has_text='incompatible').wait_for()
  state['behavior']='ok';await fp.get_by_role('button',name='Retry events',exact=True).click();await logs_ready()
  passed('fixture backend empty, HTTP failure, malformed records and wrong-session response are distinct; retry works')
  state['behavior']='hold';await fp.get_by_label('Requested event limit',exact=True).select_option('200')
  for _ in range(100):
   if state['held']:break
   await asyncio.sleep(.05)
  assert state['held']
  old_session=state['terminal']['session_id'];state['terminal']['process_id']='replacement-process';state['terminal']['session_id']='replacement-session';state['events']=[event(777,message='New-session-only')];state['behavior']='ok'
  await fp.get_by_text('New-session-only',exact=True).wait_for()
  for release,data in state['held']:release.set()
  await fp.wait_for_timeout(350)
  assert not await fp.get_by_text('Fixture message 1',exact=True).count()
  assert await fp.get_by_text('New-session-only',exact=True).count()==1
  passed('fixture in-flight old process/session response cannot seed replacement Logs')
  # Same-session reconnect retires pending requests using the synchronous connection epoch.
  state['held']=[];state['behavior']='hold';await fp.get_by_label('Requested event limit',exact=True).select_option('100')
  for _ in range(100):
   if state['held']:break
   await asyncio.sleep(.05)
  assert state['held'];state['paused']=True
  state['events']=[event(888,message='Reconnect-epoch-only')];state['behavior']='ok'
  await fp.evaluate("async()=>{const s=(await import('/src/stores/terminal.ts')).useTerminalStore;s.getState().setWsState('disconnected');s.getState().setWsState('connected');}")
  for release,data in state['held']:release.set()
  state['paused']=False
  await fp.get_by_text('Reconnect-epoch-only',exact=True).wait_for()
  assert not await fp.get_by_text('New-session-only',exact=True).count()
  passed('fixture batched same-session disconnect/reconnect retires pending response by connection epoch')
  state['paused']=True
  await fp.evaluate("async()=> (await import('/src/stores/terminal.ts')).useTerminalStore.getState().setWsState('disconnected')")
  await fp.get_by_text('Historical event evidence',exact=False).wait_for()
  count=len([r for r in state['requests'] if '/terminal/events' in r['url']]);await fp.wait_for_timeout(5400)
  assert len([r for r in state['requests'] if '/terminal/events' in r['url']])==count
  async with fp.expect_download() as dl:await fp.get_by_role('button',name='Export loaded events (bounded session evidence)',exact=True).click()
  exported=json.loads(Path(await (await dl.value).path()).read_text());assert exported['display_state']=='HISTORICAL'
  passed('fixture disconnected evidence freezes with historical export and no five-second event polling')
  state['paused']=False;await fp.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED')
  # Invalid frames preserve the accepted evidence and add existing rejection diagnostics.
  accepted=await fp.evaluate("async()=> (await import('/src/stores/terminal.ts')).useTerminalStore.getState().terminal")
  for kind in ['stale','future','schema','replay']:
   bad=copy.deepcopy(accepted)
   if kind=='stale':bad['emitted_at']='2001-01-01T00:00:00Z'
   elif kind=='future':bad['emitted_at']='2099-01-01T00:00:00Z'
   elif kind=='schema':bad['category']='bad';bad['contract_version']='invalid'
   else:bad['process_id']='phase1333-fixture-process';bad['session_id']=old_session
   result=await fp.evaluate("async(f)=> (await import('/src/stores/terminal.ts')).useTerminalStore.getState().setTerminal(f)",bad)
   assert not result['accepted']
  passed('fixture rejected stale/future/malformed/replayed frames preserve accepted Logs identity')
  await fr('settings')
  await fp.evaluate("localStorage.setItem('hyperamm-display-v1',JSON.stringify({state:{dense:'bad',sidebarCollapsed:7,historySize:999999,defaultRange:'unsupported'},version:0}))")
  await fp.reload();await fp.get_by_label('Layout density',exact=True).wait_for()
  assert await fp.get_by_label('Layout density',exact=True).input_value()=='comfortable'
  assert await fp.get_by_label('History view size',exact=True).input_value()=='600'
  await fp.evaluate("localStorage.setItem('hyperamm-display-v1','{broken-json')")
  await fp.reload();await fp.get_by_label('Default chart range',exact=True).wait_for();assert await fp.get_by_label('Default chart range',exact=True).input_value()=='session'
  passed('fixture unsupported persisted values and malformed JSON hydrate safe owned defaults after refresh')
  state['terminal']['references']=None;state['terminal']['reference_consensus']=None
  await fp.get_by_text('Provider evidence unavailable.',exact=False).wait_for()
  state['terminal']['references']=copy.deepcopy(reference_fixture);state['terminal']['reference_consensus']=copy.deepcopy(consensus_fixture)
  for e in state['terminal']['references']['evidence'].values():e['stale']=True;e['healthy']=False;e['error']='Fixture stale provider';e['source_timestamp']='2026-01-01T00:00:00Z';e['age_ms']=90000
  await fp.get_by_text('REPORTED STALE',exact=True).first.wait_for()
  assert await fp.get_by_text('Fixture stale provider',exact=False).count()
  state['paused']=True;await fp.evaluate("async()=> (await import('/src/stores/terminal.ts')).useTerminalStore.getState().setWsState('disconnected')")
  await fp.get_by_text('Historical or unavailable backend evidence',exact=False).wait_for()
  assert not await fp.locator('.settingsPage .badge.good').count()
  await fp.get_by_label('Layout density',exact=True).select_option('dense')
  assert await fp.get_by_label('Layout density',exact=True).input_value()=='dense'
  await fp.set_viewport_size({'width':390,'height':844});await fp.locator('.settingsPage').screenshot(path=str(out/'settings-fixture-390.png'))
  passed('fixture unavailable/stale sources, advancing source ages and historical SystemHealth; local preferences remain editable')
  forbidden=[r for r in state['requests'] if r['method'] in ['POST','PUT','PATCH','DELETE']]
  assert not forbidden and not report['mutations']
  passed('zero trading/configuration mutations, credential controls or browser-storage export across new workflows')
  for task in tasks:task.cancel()
  await fx.close()
  waiting=await browser.new_context();await waiting.route_web_socket('**/ws/terminal',lambda ws:None)
  wp=await waiting.new_page();wp.on('pageerror',lambda e:report['page_errors'].append(str(e)))
  await wp.goto(args.url+'/#/settings');await wp.get_by_label('Layout density',exact=True).wait_for()
  await wp.get_by_text('Waiting for accepted terminal evidence.',exact=False).wait_for()
  await wp.get_by_label('Layout density',exact=True).select_option('dense')
  assert await wp.get_by_label('Layout density',exact=True).input_value()=='dense'
  passed('initial connection without any accepted snapshot still permits browser preferences; runtime remains unavailable')
  await waiting.close();await browser.close()
 if replacement:replacement.terminate();replacement.wait(timeout=15)
 assert not report['page_errors'],report['page_errors']
 (out/'browser-results.json').write_text(json.dumps(report,indent=2))
 print(json.dumps({'layout_checks':len(report['layout_checks']),'workflows':len(report['workflows']),'page_errors':report['page_errors']}),flush=True)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--url',default='http://127.0.0.1:5173');ap.add_argument('--output',required=True);ap.add_argument('--chromium',default='/usr/bin/chromium');ap.add_argument('--python',default='/workspace/.hyperamm/venv/bin/python');ap.add_argument('--backend-pid',type=int);ap.add_argument('--fixtures-only',action='store_true')
 asyncio.run(main(ap.parse_args()))
