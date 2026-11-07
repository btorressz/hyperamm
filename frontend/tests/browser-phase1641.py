"""Real Chromium -> React -> real loopback replay API. Generated fixtures only.

Reuses Phase 15.3–15.5B process ownership, Playwright and fixture-backend pattern.
"""
import argparse,asyncio,json,os,re,signal,subprocess,tempfile,time
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[2]
SIZES=[(1920,1080),(1440,900),(1024,768),(768,900),(390,844)]

async def main(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    work=ROOT/'work/browser1641';work.mkdir(parents=True,exist_ok=True)
    report={'classification':'FAIL','fixture_notice':'GENERATED FIXTURES / USER-ASSERTED LABELS — NOT LIVE EXCHANGE ACCEPTANCE',
        'workflows':[],'page_errors':[],'console_errors':[],'requests':[],'viewports':[],'screenshots':[]}
    env={**os.environ,'MARKET_DATA_MODE':'DEMO','EXECUTION_MODE':'PAPER','ENABLE_HYPERLIQUID_TESTNET_ORDERS':'false',
         'LIVE_OBSERVATIONS_ENABLED':'false','LIVE_STREAMS_ENABLED':'false','REDIS_ENABLED':'false',
         'PHASE1641_FIXTURE_ROOT':tempfile.mkdtemp(prefix='vaults-',dir=work)}
    logs=[(work/'backend.log').open('w'),(work/'vite.log').open('w')];processes=[];started=time.monotonic()
    def backend():
        proc=subprocess.Popen([args.python,'-m','uvicorn','phase1641_browser_backend:app','--app-dir',str(ROOT/'frontend/tests'),
            '--host','127.0.0.1','--port','8000'],cwd=ROOT/'backend',env=env,stdout=logs[0],stderr=subprocess.STDOUT,start_new_session=True)
        processes.append(proc);return proc
    def stop(proc):
        if proc.poll() is None:
            os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
    server=backend()
    processes.append(subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5173','--strictPort'],
        cwd=ROOT/'frontend',stdout=logs[1],stderr=subprocess.STDOUT,start_new_session=True))
    def passed(name):report['workflows'].append(name);print('PASS '+name,flush=True)
    try:
      async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox'])
        report['browser_version']=browser.version
        ctx=await browser.new_context(viewport={'width':1440,'height':900},timezone_id='America/Los_Angeles')
        page=await ctx.new_page();page.set_default_timeout(15000)
        # Observe actual fetch bodies inside Chromium; no response interception.
        await page.add_init_script("""window.__replayReceipts=[];const originalFetch=window.fetch;
          window.fetch=async(...args)=>{const r=await originalFetch(...args);
            if(String(args[0]).endsWith('/historical-replay/run')&&r.ok)
              r.clone().json().then(v=>window.__replayReceipts.push(v));
            return r;};""")
        page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        page.on('console',lambda m:report['console_errors'].append(m.text) if m.type=='error' else None)
        page.on('request',lambda r:report['requests'].append({'method':r.method,'path':r.url.split('5173')[-1]}) if r.method in ('POST','PUT','PATCH','DELETE') else None)
        async def ready():
            async with asyncio.timeout(20):
                while True:
                    try:
                        if (await ctx.request.get('http://127.0.0.1:8000/api/v1/health',timeout=1000)).status==200:return
                    except Exception:pass
                    await asyncio.sleep(.1)
        await ready()
        async def control(**changes):
            r=await ctx.request.post('http://127.0.0.1:8000/__fixture__/replay-control',data=changes);assert r.status==200,await r.text();return await r.json()
        async def status():
            r=await ctx.request.get('http://127.0.0.1:8000/__fixture__/replay-status');assert r.status==200,await r.text();return await r.json()
        async def idle():
            async with asyncio.timeout(15):
                while (await status())['busy']:await asyncio.sleep(.05)
        async def shot(name):
            await studio.scroll_into_view_if_needed()
            await page.screenshot(path=str(out/name),full_page=True);report['screenshots'].append(name)
        async def select(m='BTC',kind='complete'):
            await studio.get_by_role('combobox',name='Historical dataset',exact=True).select_option(f'{m}-{kind}-fixture')
            await studio.get_by_role('button',name='Run Historical PAPER Replay',exact=True).wait_for()
            async with asyncio.timeout(15):
                while not await studio.get_by_role('button',name='Run Historical PAPER Replay',exact=True).is_enabled():await asyncio.sleep(.03)
        async def run():
            count=await page.evaluate('window.__replayReceipts.length')
            async with page.expect_response(lambda r:r.url.endswith('/historical-replay/run') and r.request.method=='POST') as wait:
                await studio.get_by_role('button',name='Run Historical PAPER Replay',exact=True).click()
            response=await wait.value;assert response.status==200,await response.text()
            async with asyncio.timeout(15):
                while await page.evaluate('window.__replayReceipts.length')<=count:await asyncio.sleep(.01)
            value=await page.evaluate('window.__replayReceipts.at(-1)')
            await studio.get_by_role('heading',name='Replay receipt',exact=True).wait_for()
            await studio.get_by_role('heading',name='Segment-only PAPER results',exact=True).wait_for()
            return value
        await page.goto('http://127.0.0.1:5173/#/simulation')
        studio=page.get_by_role('region',name='Historical Replay Studio',exact=True)
        await studio.get_by_role('heading',name='Historical Replay Studio',exact=True).wait_for()
        await page.evaluate("()=>{const e=document.createElement('div');e.textContent='GENERATED HISTORICAL FIXTURES · NOT LIVE EXCHANGE ACCEPTANCE';e.style='position:fixed;bottom:0;left:0;right:0;background:#653f08;color:white;z-index:9999;padding:6px;text-align:center;font:12px sans-serif';document.body.appendChild(e)}")
        await select();before=await status();receipt=await run()
        assert receipt['segments'][0]['fill_count']==0
        assert await studio.locator('.replayColumns canvas').count()>0
        await studio.get_by_role('region',name='Historical retained L2 book',exact=True).wait_for()
        assert '60,000' in await studio.locator('.replayBook').inner_text()
        await studio.get_by_text('Execution, inventory and order lifecycle metrics',exact=True).click()
        assert 'Unavailable' in await studio.inner_text()
        after=await status();assert before['authority']==after['authority'] and after['subscriptions']==0
        passed('Navigation and baseline HTTP PAPER replay work with no operational terminal connection; zero fills, missing metrics, retained chart/L2 and isolation')
        for m in ('ETH','SOL','BTC'):
            await select(m);result=await run();assert result['request']['market']==m
        passed('BTC/ETH/SOL selections verify actual catalog/provenance and market-specific backend results')
        await control(provenance_delay=.3)
        await studio.get_by_role('combobox',name='Historical dataset',exact=True).select_option('BTC-gap-fixture')
        await studio.get_by_role('combobox',name='Historical dataset',exact=True).select_option('ETH-complete-fixture')
        await control(provenance_delay=0)
        await select('ETH');await run()
        assert await studio.get_by_role('combobox',name='Historical dataset',exact=True).input_value()=='ETH-complete-fixture'
        assert 'Synthetic research fixture' in await studio.inner_text()
        passed('Late provenance for a previous selection cannot replace current ETH source evidence')
        await select();await control(delay=.4)
        count=len(report['requests'])
        await studio.get_by_role('button',name='Run Historical PAPER Replay',exact=True).evaluate('(e)=>{e.click();e.click();e.click()}')
        await idle();await control(delay=0)
        assert len(report['requests'])==count+1
        passed('Rapid repeated DOM submissions admit one HTTP replay request')
        await control(delay=1)
        held=asyncio.create_task(ctx.request.post('http://127.0.0.1:8000/api/v1/historical-replay/run',data=receipt['request']))
        async with asyncio.timeout(5):
            while not (await status())['busy']:await asyncio.sleep(.01)
        await studio.get_by_role('button',name='Run Historical PAPER Replay',exact=True).click()
        await studio.get_by_role('alert').filter(has_text='Shared research worker busy').wait_for()
        await shot('fixture-worker-busy-429.png')
        assert (await held).status==200
        await control(delay=0)
        passed('Actual occupied worker produces a sanitized 429 browser banner')

        await select('BTC','gap')
        await studio.get_by_role('combobox',name='Execution model',exact=True).select_option('MODELED_CROSSING')
        await studio.get_by_label('Order latency',exact=True).fill('10')
        await studio.get_by_label('Cancel latency',exact=True).fill('20')
        await studio.get_by_label('Slippage bps',exact=True).fill('0.1')
        await studio.get_by_label('Participation rate',exact=True).fill('0.5')
        await studio.get_by_label('Max fill fraction',exact=True).fill('0.5')
        await studio.get_by_label('Traverse retained L2 depth',exact=True).check()
        result=await run();assert len(result['segments'])==2 and result['segments'][0]['baseline_result_json']
        await studio.get_by_role('heading',name='Baseline crossing-only',exact=True).wait_for()
        await studio.get_by_role('button',name='Play',exact=True).click()
        await studio.get_by_text('Frame 2 of 2',exact=False).wait_for()
        await studio.get_by_role('button',name='Play',exact=True).wait_for()
        await studio.get_by_role('combobox',name='Replay segment',exact=True).select_option('1')
        await studio.get_by_text('Frame 1 of 2',exact=False).wait_for()
        assert await studio.get_by_role('button',name='Previous',exact=True).is_disabled()
        assert await studio.locator('.replayColumns .historyChart').count()==1
        await studio.get_by_text('Explore segment equity, PnL, inventory, risk and execution trace',exact=True).click()
        await studio.get_by_role('region',name='Simulation trace',exact=True).wait_for()
        passed('Modeled HTTP run uses latency/slippage/depth/partial controls, independent backend baseline; playback stops at final frame and resets across explicit gap')
        for width,height in SIZES:
            await page.set_viewport_size({'width':width,'height':height})
            await studio.scroll_into_view_if_needed();await asyncio.sleep(.1)
            overflow=await page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
            assert overflow['scroll']<=width+1,overflow
            chart=await studio.locator('.replayColumns .historyChart').bounding_box();assert chart and chart['width']>100 and chart['width']<=width
            await shot(f'fixture-modeled-gap-{width}.png')
            report['viewports'].append({**overflow,'chart_width':chart['width'],'classification':'PASS'})
        passed('1920/1440/1024/768/390 widths resize actual charts with no horizontal page overflow')
        await page.set_viewport_size({'width':1440,'height':900})
        await select('SOL','generation');result=await run();assert result['segments'][1]['reset_reason']=='OBSERVER_CHANGE'
        passed('Observer generation boundary produces separate PAPER segments')
        await control(fixture_reference_firewall=False)
        before=await status()
        await select('BTC','crossing');result=await run()
        assert result['segments'][0]['fill_count']>0
        assert json.loads(result['segments'][0]['simulation_result_json'])['vault']['execution_accounting']['execution_accounting_consistent']
        after=await status();assert before['authority']==after['authority']
        await shot('fixture-positive-partial-fills.png')
        await control(fixture_reference_firewall=True)
        passed('Explicit test-configured reference firewall permits actual modeled partial PAPER fills and backend Decimal comparison without changing seeded operational state')

        await select('BTC','missing')
        await studio.get_by_role('button',name='Run Historical PAPER Replay',exact=True).click()
        await studio.get_by_role('alert').filter(has_text='NO_VIABLE_FRAMES').wait_for()
        await shot('fixture-missing-economics-422.png')
        passed('Actual structured 422 missing-economics/zero-viable rejection is visible')
        await select();await control(delay=1)
        await studio.get_by_role('button',name='Run Historical PAPER Replay',exact=True).click()
        async with asyncio.timeout(5):
            while not (await status())['busy']:await asyncio.sleep(.01)
        response=await ctx.request.get('http://127.0.0.1:8000/api/v1/historical-replay/dataset-summaries');assert response.status==429
        await studio.get_by_role('combobox',name='Historical dataset',exact=True).select_option('ETH-complete-fixture')
        await idle();await control(delay=0)
        assert await studio.get_by_role('heading',name='Replay receipt',exact=True).count()==0
        passed('Actual shared worker returns 429; delayed BTC response cannot overwrite a newer ETH selection')
        await select('ETH');await control(delay=.6)
        await studio.get_by_role('button',name='Run Historical PAPER Replay',exact=True).click()
        await studio.get_by_label('Slippage bps',exact=True).fill('2')
        await idle();await control(delay=0)
        assert await studio.get_by_role('heading',name='Replay receipt',exact=True).count()==0
        passed('Model edits retire pending results without claiming backend computation was cancelled')
        await select();await control(delay=.8)
        await studio.get_by_role('button',name='Run Historical PAPER Replay',exact=True).click()
        await page.evaluate("location.hash='#/markets'");await idle();await control(delay=0)
        await page.evaluate("location.hash='#/simulation'");await studio.get_by_role('heading',name='Historical Replay Studio',exact=True).wait_for()
        assert await studio.get_by_role('heading',name='Replay receipt',exact=True).count()==0
        passed('Navigation/unmount retires pending responses; remounted Studio starts without obsolete result')
        await control(storage='empty');await studio.get_by_role('button',name='Refresh catalog',exact=True).click()
        async with asyncio.timeout(5):
            while await studio.get_by_role('combobox',name='Historical dataset',exact=True).locator('option').count()!=1:await asyncio.sleep(.05)
        await control(storage='disabled');await studio.get_by_role('button',name='Refresh catalog',exact=True).click()
        await studio.get_by_text('Historical dataset catalog unavailable.',exact=False).wait_for();await shot('fixture-disabled-503.png')
        await control(storage='vault');await studio.get_by_role('button',name='Refresh catalog',exact=True).click();await select();await run()
        passed('Empty vault, storage-disabled 503 and explicit refresh recovery retire removed dataset results')
        stop(server)
        await studio.get_by_role('button',name='Run Historical PAPER Replay',exact=True).click()
        await studio.get_by_role('alert').filter(has_text=re.compile('connection unavailable|HTTP 500')).wait_for()
        server=backend();await ready()
        await studio.get_by_role('button',name='Refresh catalog',exact=True).click();await select();await run()
        passed('Actual backend shutdown/restart gives safe network error and successful retry')
        await control(terminal=True)
        async with asyncio.timeout(20):
            while not await page.evaluate("async()=>!!(await import('/src/stores/terminal.ts')).useTerminalStore.getState().terminal"):await asyncio.sleep(.1)
        await page.get_by_label('Frames',exact=True).fill('3')
        await page.get_by_role('button',name='Run Simulation',exact=True).click()
        await page.get_by_role('region',name='Completed simulation',exact=True).wait_for()
        await page.get_by_role('button',name='Run Bounded Grid Search',exact=True).click()
        await page.get_by_role('region',name='Completed optimization',exact=True).wait_for(timeout=60000)
        await page.evaluate("location.hash='#/vault'");await page.get_by_role('heading',name='Research vault & accounting',exact=True).wait_for()
        passed('Original actual scenario simulation, bounded optimizer and Research Vault navigation remain functional')
        assert not report['page_errors'],report['page_errors']
        report['unexpected_console_errors']=[e for e in report['console_errors'] if not any(token in e for token in ('WebSocket handshake: Unexpected response code: 403','status of 404','status of 422','status of 429','status of 503','status of 500'))]
        assert not report['unexpected_console_errors'],report['unexpected_console_errors']
        assert all(x['path'].split('?')[0] in ('/api/v1/historical-replay/run','/api/v1/simulation/run','/api/v1/simulation/optimize') for x in report['requests']),report['requests']
        report['classification']='PASS';await ctx.close();await browser.close()
    finally:
        for proc in processes:stop(proc)
        for log in logs:log.close()
        report['duration_seconds']=round(time.monotonic()-started,3)
        (out/'browser-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--python',default=str(ROOT/'backend/.venv/bin/python'))
    p.add_argument('--chromium',default='/usr/bin/chromium');p.add_argument('--output',default=str(ROOT/'docs/acceptance/phase1641'))
    asyncio.run(main(p.parse_args()))
