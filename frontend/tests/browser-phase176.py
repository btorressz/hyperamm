"""Real Chromium -> React -> bounded local API -> admitted native PAPER engines.

Faults and disconnected transport are explicitly controlled by the test-only
harness. No mocked financial responses in the primary workflows.
"""
import argparse,asyncio,json,os,signal,subprocess,time
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[2]
KINDS=['CORRELATED_SELLOFF','BTC_LED_VOLATILITY','LIQUIDITY_SHOCK','FUNDING_STRESS','ORACLE_DEGRADATION','CONCENTRATION_STRESS']

async def main(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    report={'classification':'FAIL','workflows':[],'page_errors':[],'console_errors':[],'expected_fault_console':[],'measurements':[],'viewports':[]}
    env={**os.environ,'MARKET_DATA_MODE':'DEMO','EXECUTION_MODE':'PAPER','ENABLE_HYPERLIQUID_TESTNET_ORDERS':'false',
        'LIVE_STREAMS_ENABLED':'false','LIVE_OBSERVATIONS_ENABLED':'false','REDIS_ENABLED':'false'}
    logs=[(out/'backend.log').open('w'),(out/'vite.log').open('w')]
    processes=[subprocess.Popen([args.python,'-m','uvicorn','phase176_browser_backend:app','--app-dir',str(ROOT/'frontend/tests'),
        '--host','127.0.0.1','--port','8000'],cwd=ROOT/'backend',env=env,stdout=logs[0],stderr=subprocess.STDOUT,start_new_session=True),
        subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5173','--strictPort'],cwd=ROOT/'frontend',stdout=logs[1],stderr=subprocess.STDOUT,start_new_session=True)]
    def passed(name):report['workflows'].append(name);print('PASS '+name,flush=True)
    try:
      async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox'])
        report['browser_version']=browser.version
        ctx=await browser.new_context(viewport={'width':1440,'height':1000})
        await ctx.add_init_script("""window.__portfolioWire=[];const nativeFetch=window.fetch;window.fetch=async(...a)=>{
          const r=await nativeFetch(...a);if(String(a[0]).includes('/portfolio-research/')){
            const entry={path:String(a[0]),status:r.status,body:null};window.__portfolioWire.push(entry);
            r.clone().text().then(t=>entry.body=t).catch(()=>entry.body='{}');}return r;};""")
        page=await ctx.new_page();page.set_default_timeout(60000)
        faults=False
        page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        page.on('console',lambda m:(report['expected_fault_console'] if faults else report['console_errors']).append(m.text) if m.type=='error' else None)
        async def control(**kw):return await (await ctx.request.post('http://127.0.0.1:8000/__fixture__/portfolio-control',data=kw)).json()
        async def status():return await (await ctx.request.get('http://127.0.0.1:8000/__fixture__/portfolio-status')).json()
        async with asyncio.timeout(30):
          while True:
            try:
              if (await ctx.request.get('http://127.0.0.1:8000/api/v1/health',timeout=1000)).status==200:break
            except Exception:pass
            await asyncio.sleep(.1)
        before=(await status())['authority']
        catalog=await (await ctx.request.get('http://127.0.0.1:8000/api/v1/research-markets')).json()
        assert [m['market'] for m in catalog['markets']]==['BTC','ETH','SOL']
        assert all(m['research_supported'] for m in catalog['markets'])
        report['configured_catalog']=[{k:m[k] for k in ('market','metadata_source','metadata_status','profile_fingerprint','sz_decimals')} for m in catalog['markets']]
        passed('Actual configured lifespan catalog loads BTC/ETH/SOL with official loader and eligible profiles')
        await page.goto('http://127.0.0.1:5173/#/portfolio-research')
        await page.get_by_role('heading',name='Portfolio Research',exact=True).wait_for()
        await page.get_by_label('Frames per market',exact=True).fill('12')
        await asyncio.sleep(2)
        assert (await status())['runs']==0
        passed('Dedicated page and local controls available without terminal WebSocket; no automatic simulation')
        async def section(name):await page.get_by_role('navigation',name='Portfolio workspace sections').get_by_role('button',name=name,exact=True).click()
        async def read_wire(path):
          await page.wait_for_function("path=>window.__portfolioWire.filter(e=>e.path.endsWith(path)).at(-1)?.body!==null && !!window.__portfolioWire.filter(e=>e.path.endsWith(path)).at(-1)",arg=path)
          text=await page.evaluate("path=>window.__portfolioWire.filter(e=>e.path.endsWith(path)).at(-1).body",path)
          return json.loads(text),len(text.encode())
        async def preview(expected=200):
          async with page.expect_response(lambda r:r.url.endswith('/portfolio-research/preview')) as pending:
            await page.get_by_role('button',name='Validate / Preview',exact=True).click()
          r=await pending.value;assert r.status==expected,r.status
          if expected==200:
            data,size=await read_wire('/preview');assert data['config_fingerprint']==data['config_fingerprint'].lower();report['measurements'].append({'kind':'preview','bytes':size})
            await page.get_by_role('button',name='Run PAPER portfolio',exact=True).wait_for(state='visible')
            await page.wait_for_function("!Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Run PAPER portfolio').disabled")
          return data if expected==200 else {}
        async def execute(button,mode):
          runs_before=(await status())['runs']
          async with page.expect_response(lambda r:r.url.endswith('/portfolio-research/terminal'),timeout=120000) as pending:
            await page.get_by_role('button',name=button,exact=True).click()
          r=await pending.value;assert r.status==200,r.status;data,size=await read_wire('/terminal')
          report['measurements'].append({'kind':mode,'bytes':size,'points':len(data['baseline']['charts']['points'])})
          assert data['mode']==mode and data['authority']=='NONE'
          expected=len(data['baseline']['markets'])*(2 if mode=='STRESS' else 1)
          assert (await status())['runs']-runs_before==expected,'duplicate engine execution'
          report['measurements'][-1]['native_runs']=expected
          report['measurements'][-1]['request_bytes']=len(r.request.post_data_buffer)
          await page.get_by_text('Accepted research evidence is available in Analytics.',exact=True).wait_for()
          return data
        await preview();r=await execute('Run PAPER portfolio','RUN');assert r['baseline']['charts']['status']=='AVAILABLE'
        await section('Analytics');await page.get_by_role('heading',name='Baseline Portfolio Analytics',exact=True).wait_for()
        await page.get_by_label('Chart metric',exact=True).select_option('pnl_quote');await page.get_by_label('Chart metric',exact=True).select_option('drawdown_fraction')
        passed('Three-market PAPER run, accounting, risk and eligible equity/PnL/drawdown charts')
        for selection in (('BTC',),('ETH','SOL')):
          await section('Configure')
          for market in ('BTC','ETH','SOL'):
            await page.get_by_label(market+'-PERP',exact=True).set_checked(market in selection)
          await preview();r=await execute('Analyze portfolio','ANALYZE')
          assert [m['market'] for m in r['baseline']['markets']]==list(selection)
          passed('Native market selection: '+','.join(selection))
        await section('Configure')
        for market in ('BTC','ETH','SOL'):await page.get_by_label(market+'-PERP',exact=True).check()
        for market,amount in (('BTC','40000'),('ETH','35000'),('SOL','20000')):
          await page.get_by_label(market+' allocation (USDC)',exact=True).fill(amount)
        await page.get_by_label('Total hypothetical capital (USDC)',exact=True).fill('100000.000000000000000001')
        await page.get_by_label('Minimum reserve (USDC)',exact=True).fill('5000.000000000000000001')
        prepared=await preview()
        assert prepared['reserve_quote']=='5000.000000000000000001'
        assert all(s['captured']['market_profile_fingerprint']==next(m['profile_fingerprint'] for m in report['configured_catalog'] if m['market']==s['market']) for s in prepared['config']['scenarios'])
        passed('Exact 18-place shared capital/reserve and server-authoritative configured catalog fingerprints')
        await page.get_by_label('Total hypothetical capital (USDC)',exact=True).fill('100000')
        await page.get_by_label('Minimum reserve (USDC)',exact=True).fill('5000')
        await section('Stress Lab');await page.get_by_label('Prepare baseline versus stressed comparison',exact=True).check()
        await page.get_by_label('Shock onset (zero-based frame)',exact=True).fill('7');await page.get_by_label('Shock duration (frames)',exact=True).fill('5')
        for kind in KINDS:
          await section('Stress Lab');await page.get_by_label('Stress scenario',exact=True).select_option(kind)
          await preview();r=await execute('Run baseline + stress','STRESS');assert r['stressed'] and r['stressed']['charts']['status']=='AVAILABLE'
          await section('Analytics');await page.get_by_role('heading',name='Baseline versus stressed comparison',exact=True).wait_for()
          passed('Native baseline/stress: '+kind)
        await page.evaluate('window.scrollTo(0,0)');await page.screenshot(path=str(out/'desktop.png'),full_page=True)
        await section('Provenance');await page.get_by_text('Configuration fingerprint',exact=True).wait_for()
        assert 'not cryptographic signatures' in await page.locator('body').inner_text()
        passed('Provenance: canonical configuration, datasets, accounting, original results and chart fingerprints')
        for w,h in [(1920,1080),(1440,1000),(1024,768),(768,900),(390,844)]:
          await page.set_viewport_size({'width':w,'height':h});await section('Analytics')
          await page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
          assert await page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1'),f'overflow at {w}'
          charts=await page.locator('.portfolioWorkspace canvas').evaluate_all('els=>els.map(e=>e.getBoundingClientRect().width)')
          assert charts and all(0 < width <= w for width in charts),f'chart bounds at {w}: {charts}'
          tables=await page.locator('.portfolioWorkspace .tableWrap').evaluate_all("els=>els.map(e=>({width:e.getBoundingClientRect().width,overflow:getComputedStyle(e).overflowX}))")
          assert all(t['width']<=w and t['overflow'] in ('auto','scroll') for t in tables)
          sections=[]
          for name in ('Configure','Analytics','Stress Lab','Provenance'):
            await section(name)
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),f'{name} overflow at {w}'
            missing=await page.locator('input:not([type=hidden]),select').evaluate_all("els=>els.filter(e=>!e.labels?.length&&!e.getAttribute('aria-label')).length")
            assert missing==0
            sections.append(name)
          report['viewports'].append({'width':w,'height':h,'overflow':False,'sections':sections,'unlabeled_controls':0,'chart_widths':charts,'scrollable_tables':len(tables)})
        await page.evaluate('window.scrollTo(0,0)');await page.screenshot(path=str(out/'mobile.png'),full_page=True)
        await page.get_by_role('button',name='Open navigation',exact=True).click();await page.get_by_role('dialog',name='Terminal navigation').wait_for()
        await page.keyboard.press('Escape');assert not await page.get_by_role('button',name='Open navigation',exact=True).get_attribute('aria-expanded')=='true'
        await page.get_by_role('button',name='Open navigation',exact=True).focus()
        await page.keyboard.press('Tab');await page.keyboard.press('Shift+Tab')
        assert await page.get_by_role('button',name='Open navigation',exact=True).evaluate("e=>getComputedStyle(e).outlineStyle!=='none' && parseFloat(getComputedStyle(e).outlineWidth)>0")
        await page.keyboard.press('Enter');await page.get_by_role('link',name='Portfolio Research',exact=True).click()
        await section('Configure');await page.get_by_label('Total hypothetical capital (USDC)',exact=True).fill('1')
        assert await page.get_by_role('button',name='Validate / Preview',exact=True).is_disabled()
        await page.get_by_role('alert').filter(has_text='Allocations exceed total').wait_for()
        await page.get_by_label('Total hypothetical capital (USDC)',exact=True).fill('100000')
        passed('Desktop/tablet/mobile responsive sections, keyboard drawer and actionable exact allocation validation')
        await page.set_viewport_size({'width':1440,'height':1000})
        await section('Stress Lab');await page.get_by_label('Stress scenario',exact=True).select_option('CORRELATED_SELLOFF');await section('Configure')
        # Execute the actual native retention boundary, then inspect unavailable evidence.
        await page.get_by_label('Frames per market',exact=True).fill('300');await preview()
        r=await execute('Run baseline + stress','STRESS')
        assert r['baseline']['temporal']['classification']=='FINAL_ONLY' and r['baseline']['accounting']['drawdown'] is None
        assert r['baseline']['risk']['outcome']=='BLOCKED' and r['baseline']['risk']['decision']=='HALT'
        await section('Analytics');await page.get_by_text('Chart Unavailable',exact=False).first.wait_for()
        passed('Actual FINAL_ONLY native stress: unavailable drawdown/charts, BLOCKED risk with known HALT')
        await section('Configure')
        await page.get_by_role('status').filter(has_text='Estimated FINAL_ONLY:').wait_for()
        await page.get_by_label('Frames per market',exact=True).fill('12')
        # Actual busy and cancellation probes use the same admitted worker.
        await preview();await control(delay=.4)
        async with page.expect_request(lambda r:r.url.endswith('/portfolio-research/terminal')):
          await page.get_by_role('button',name='Run baseline + stress',exact=True).click()
        async with asyncio.timeout(15):
          while not (await status())['busy']:await asyncio.sleep(.05)
        await page.get_by_role('button',name='Stop waiting',exact=True).click()
        assert (await status())['busy']
        await section('Analytics');await page.get_by_text('No accepted result for the current draft.',exact=False).wait_for()
        await section('Configure');await preview();faults=True
        async with page.expect_response(lambda r:r.url.endswith('/portfolio-research/terminal')) as pending:
          await page.get_by_role('button',name='Run PAPER portfolio',exact=True).click()
        assert (await pending.value).status==429
        await page.get_by_role('alert').filter(has_text='Shared research worker busy').wait_for()
        async with asyncio.timeout(30):
          while (await status())['busy']:await asyncio.sleep(.1)
        await control(delay=0)
        passed('Browser abort does not release worker; actual 429 busy state; retired result never returns')
        # A real failed fetch, with no successful financial response fabricated.
        await ctx.route('**/api/v1/portfolio-research/preview',lambda route:route.abort('connectionrefused'))
        await page.get_by_role('button',name='Validate / Preview',exact=True).click()
        await page.get_by_role('alert').filter(has_text='Local research connection unavailable').wait_for()
        await ctx.unroute('**/api/v1/portfolio-research/preview')
        assert await page.get_by_role('button',name='Run PAPER portfolio',exact=True).is_disabled()
        passed('Unavailable backend retires preview and requires explicit validation after transport recovery')
        # Sanitized server exception.
        await control(failure=True);await preview()
        async with page.expect_response(lambda r:r.url.endswith('/portfolio-research/terminal')) as pending:
          await page.get_by_role('button',name='Run PAPER portfolio',exact=True).click()
        assert (await pending.value).status==500
        await page.get_by_role('alert').filter(has_text='HTTP 500').wait_for()
        assert '/private/secret' not in await page.locator('body').inner_text()
        await control(failure=False)
        faults=False
        passed('Sanitized HTTP 500 failure with no private diagnostics')
        # WS session transition retires REST evidence; pending requests cannot restore it.
        await preview();await control(terminal=True);await asyncio.sleep(12)
        assert await page.get_by_role('button',name='Run PAPER portfolio',exact=True).is_disabled()
        await preview();await execute('Run PAPER portfolio','RUN')
        after=(await status())['authority']
        report['authority_changed_fields']=[key for key in before if before[key]!=after[key]]
        assert after==before,report['authority_changed_fields']
        passed('Reconnect retires previous preview; explicit revalidation recovers; operational authority unchanged')
        assert not report['page_errors'],report['page_errors']
        assert not report['console_errors'],report['console_errors']
        assert all(any(expected in entry for expected in ('status of 429','status of 500','ERR_CONNECTION_REFUSED'))
                   for entry in report['expected_fault_console']),report['expected_fault_console']
        report['workflow_count']=len(report['workflows'])
        report['viewport_count']=len(report['viewports'])
        report['engine_runs']=(await status())['runs']
        report['classification']='PASS'
        await browser.close()
    finally:
      if report['classification']!='PASS' and 'page' in locals() and not page.is_closed():
        try:
          await page.screenshot(path=str(out/'failure.png'),full_page=True)
          (out/'failure.txt').write_text(await page.locator('body').inner_text())
        except Exception:pass
      (out/'acceptance.json').write_text(json.dumps(report,indent=2)+'\n')
      for proc in processes:
        if proc.poll() is None:
          os.killpg(proc.pid,signal.SIGTERM)
          try:proc.wait(timeout=15)
          except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
      for log in logs:log.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--python',default=str(ROOT/'.venv/bin/python'));parser.add_argument('--chromium',default='/usr/bin/chromium');parser.add_argument('--output',default=str(ROOT/'work/phase176-browser'))
    asyncio.run(main(parser.parse_args()))
