"""Chromium -> actual React -> actual bounded comparison API and PAPER engines.

Reuses the Phase 16.4.1 fixture server, secure dataset admission and process pattern.
No response mocks in the primary workflow; labeled fault probes are separate.
"""
import argparse, asyncio, json, os, signal, subprocess, tempfile, time
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[2]
SIZES=[(1920,1080),(1440,900),(1024,768),(768,900),(390,844)]
URL='/api/v1/research-comparison/scenario-historical'

async def main(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    work=ROOT/'work/browser165c2';work.mkdir(parents=True,exist_ok=True)
    report={'classification':'FAIL','fixture_notice':'GENERATED FIXTURES / USER-ASSERTED RECORDED LABELS; NO AUTHENTICATED EXCHANGE HISTORY',
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
        page=await ctx.new_page();page.set_default_timeout(20000)
        # Capture real fetch clones immediately; Chromium may evict a response
        # body from DevTools while rendering charts and terminal publications.
        await page.add_init_script("""window.__comparisonResponses=[];const originalFetch=window.fetch;
          window.fetch=async(...args)=>{const r=await originalFetch(...args);
            if(String(args[0]).endsWith('/research-comparison/scenario-historical'))
              r.clone().json().then(value=>window.__comparisonResponses.push({status:r.status,value}));
            return r;};""")
        page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        page.on('console',lambda m:report['console_errors'].append(m.text) if m.type=='error' else None)
        page.on('request',lambda r:report['requests'].append({'method':r.method,'path':r.url.split('5173')[-1]}) if r.method in ('POST','PUT','PATCH','DELETE') else None)
        async def ready():
            async with asyncio.timeout(30):
                while True:
                    try:
                        if (await ctx.request.get('http://127.0.0.1:8000/api/v1/health',timeout=1000)).status==200:return
                    except Exception:pass
                    await asyncio.sleep(.1)
        await ready()
        async def control(**changes):
            r=await ctx.request.post('http://127.0.0.1:8000/__fixture__/replay-control',data=changes);assert r.status==200,await r.text();return await r.json()
        async def status():return await (await ctx.request.get('http://127.0.0.1:8000/__fixture__/replay-status')).json()
        async def idle():
            async with asyncio.timeout(30):
                while (await status())['busy']:await asyncio.sleep(.05)
        await control(terminal=True)
        await page.goto('http://127.0.0.1:5173/#/simulation')
        await page.get_by_role('heading',name='Simulation & Optimization',exact=True).wait_for()
        await page.get_by_role('button',name='Historical replay',exact=True).click()
        await page.get_by_role('heading',name='Historical Replay Studio',exact=True).wait_for()
        await page.get_by_role('button',name='Scenario vs historical',exact=True).click()
        studio=page.get_by_role('region',name='Scenario vs Historical Replay Comparison Studio',exact=True)
        async def enabled():
            async with asyncio.timeout(30):
                while not await studio.get_by_role('button',name='Run Scenario / Historical Comparison',exact=True).is_enabled():await asyncio.sleep(.05)
        async def select(m='BTC',kind='complete',scenario_market=None):
            await studio.get_by_role('combobox',name='Research Perpetual Market',exact=True).select_option(scenario_market or m)
            await studio.get_by_role('combobox',name='Historical dataset',exact=True).select_option(f'{m}-{kind}-fixture')
            await studio.get_by_role('spinbutton',name='Scenario frames',exact=True).fill('4')
            await studio.get_by_role('spinbutton',name='Maximum frames',exact=True).fill('4')
            await enabled()
        async def run(expected=200):
            await enabled()
            count=await page.evaluate('window.__comparisonResponses.length')
            async with page.expect_response(lambda r:r.url.endswith(URL) and r.request.method=='POST') as wait:
                await studio.get_by_role('button',name='Run Scenario / Historical Comparison',exact=True).click()
            response=await wait.value;assert response.status==expected,await response.text()
            async with asyncio.timeout(15):
                while await page.evaluate('window.__comparisonResponses.length')<=count:await asyncio.sleep(.02)
            value=await page.evaluate('window.__comparisonResponses.at(-1).value')
            if expected==200:await studio.get_by_role('heading',name='Research pairing status',exact=True).wait_for()
            return value
        async def shot(name):
            await studio.scroll_into_view_if_needed();await page.screenshot(path=str(out/name),full_page=True);report['screenshots'].append(name)
        await select();before=await status();result=await run();after=await status()
        assert before['authority']==after['authority'] and before['subscriptions']==after['subscriptions']
        assert result['receipt']['foundation']['classification']=='CONTEXT_ONLY'
        assert await studio.locator('canvas').count()>=12
        await studio.get_by_text('Matching configuration identities',exact=True).wait_for()
        await studio.get_by_text('Differing configuration identities',exact=True).wait_for()
        await studio.get_by_text('Inspect exact fingerprints',exact=True).click()
        await studio.get_by_text(result['receipt']['receipt_fingerprint'],exact=True).wait_for()
        await studio.get_by_text('Execution & fills',exact=False).first.click()
        fills=studio.get_by_role('row').filter(has=page.get_by_role('rowheader',name='Hypothetical fills',exact=False))
        assert await fills.get_by_role('cell').nth(1).inner_text()=='0 fills'
        missing=studio.get_by_role('row').filter(has=page.get_by_role('rowheader',name='Fill activity ratio',exact=False))
        assert 'Unavailable' in await missing.inner_text()
        await shot('btc-context-and-traces-1440.png')
        passed('Actual BTC comparison, backend metrics, zero fills, unavailable metric, separate original charts, inspectable provenance, operational isolation')
        for width,height in SIZES:
            await page.set_viewport_size({'width':width,'height':height});await asyncio.sleep(.2)
            overflow=await page.evaluate('({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth})')
            assert overflow['scroll']<=overflow['client']+1,overflow
            widths=await studio.locator('.researchChart canvas').evaluate_all('(nodes)=>nodes.map(n=>n.getBoundingClientRect().width)')
            assert all(0<w<=width for w in widths),widths
            await shot(f'comparison-{width}.png');report['viewports'].append({'width':width,'height':height,'overflow':False,'chart_count':len(widths)})
        await page.set_viewport_size({'width':1440,'height':900})
        passed('1920/1440/1024/768/390 responsive layouts, chart resizing, wrapped fingerprints and decimal cells')
        for market in ('ETH','SOL'):
            await select(market);r=await run();assert r['receipt']['foundation']['classification']=='CONTEXT_ONLY'
        passed('Actual ETH and SOL comparisons')
        await select(kind='gap');r=await run();assert r['segment_count']==2 and r['declared_gaps']
        async with page.expect_response(lambda r:r.url.endswith(URL)) as wait:
            await studio.get_by_role('combobox',name='Comparison historical segment',exact=True).select_option('1')
        assert (await wait.value).status==200
        await studio.get_by_text('Segment 2 / 2',exact=False).wait_for()
        await studio.get_by_text('Receipt gaps and excluded evidence',exact=True).click()
        await shot('independent-gap-segment-2.png')
        passed('Multi-segment gap with explicit reset and validated selected-segment rerun')
        await select();await studio.get_by_role('combobox',name='Execution model',exact=True).select_option('MODELED_CROSSING')
        await studio.get_by_role('spinbutton',name='Order latency',exact=True).fill('1')
        r=await run();assert 'EXECUTION_MISMATCH' in r['receipt']['foundation']['reasons']
        passed('Actual modeled PAPER execution with explicit configuration differences')
        await studio.get_by_role('combobox',name='Execution model',exact=True).select_option('BASELINE')
        await select('ETH',scenario_market='BTC');r=await run()
        assert r['receipt']['display_policy']=='BLOCKED' and not r['receipt']['rows']
        assert not await studio.get_by_role('table').count()
        assert not await studio.locator('canvas').count()
        await shot('market-incomparable.png');passed('Cross-market INCOMPARABLE blocks financial metrics and traces')
        await select();await control(delay=.5)
        async with page.expect_request(lambda r:r.url.endswith(URL)):
            await studio.get_by_role('button',name='Run Scenario / Historical Comparison',exact=True).click()
        await studio.get_by_role('combobox',name='Research Perpetual Market',exact=True).select_option('ETH')
        await studio.get_by_role('combobox',name='Historical dataset',exact=True).select_option('ETH-complete-fixture')
        await idle();await asyncio.sleep(.2)
        assert not await studio.get_by_role('heading',name='Research pairing status',exact=True).count()
        passed('Pending market/dataset changes retire late real backend responses')
        await control(delay=0)
        await select(kind='missing');await run(422);await studio.get_by_role('alert').filter(has_text='rejected').wait_for()
        await select();await control(storage='disabled');await run(503);await studio.get_by_role('alert').filter(has_text='unavailable').wait_for()
        await control(storage='vault',delay=1)
        held=asyncio.create_task(ctx.request.post('http://127.0.0.1:8000'+URL,data=result['request']))
        async with asyncio.timeout(10):
            while not (await status())['busy']:await asyncio.sleep(.03)
        await run(429);await studio.get_by_role('alert').filter(has_text='busy').wait_for()
        assert (await held).status==200;await idle();await control(delay=0)
        passed('Real 422 missing economics, 503 disabled vault, 429 single-worker busy errors')
        # Explicit malformed-response fault probe, separate from native workflows.
        await page.route('**'+URL,lambda route:route.fulfill(status=200,content_type='application/json',body='{"version":"invalid"}'))
        await enabled();await studio.get_by_role('button',name='Run Scenario / Historical Comparison',exact=True).click()
        await studio.get_by_role('alert').filter(has_text='rejected').wait_for()
        assert not await studio.get_by_role('heading',name='Research pairing status',exact=True).count()
        await page.unroute('**'+URL);passed('Labeled malformed-response fault probe fails closed')
        await run();await studio.get_by_role('spinbutton',name='Scenario frames',exact=True).fill('5')
        await studio.get_by_text('Retired result:',exact=False).wait_for()
        assert not await studio.get_by_role('heading',name='Research pairing status',exact=True).count()
        passed('Frame edits hide stale metrics with captured retired identity')
        await studio.get_by_role('spinbutton',name='Scenario frames',exact=True).focus();await page.keyboard.press('Tab')
        assert await page.evaluate('document.activeElement.tagName') in ('INPUT','SELECT','BUTTON','SUMMARY')
        passed('Keyboard form navigation and native disclosures')
        await select();await control(delay=.5)
        await studio.get_by_role('button',name='Run Scenario / Historical Comparison',exact=True).click()
        async with asyncio.timeout(10):
            while not (await status())['busy']:await asyncio.sleep(.03)
        await page.get_by_role('button',name='Historical replay',exact=True).click()
        assert (await status())['busy']
        await idle();await control(delay=0)
        await page.get_by_role('button',name='Scenario vs historical',exact=True).click()
        assert not await studio.get_by_role('heading',name='Research pairing status',exact=True).count()
        passed('Unmount cancels HTTP waiter, worker capacity retained, remount has no stale result')
        await select();await run();saved_identity=result['provenance']['dataset_fingerprint']
        stop(server);server=backend();await ready();await control(terminal=True)
        await studio.get_by_text('Retired result:',exact=False).wait_for(timeout=30000)
        assert not await studio.get_by_role('heading',name='Research pairing status',exact=True).count()
        await select();r=await run();assert r['provenance']['dataset_fingerprint']==saved_identity
        passed('Backend restart retires receipts; retained admitted evidence reproduces identity')
        # Existing workspace regressions use their actual engines and API.
        await page.get_by_role('button',name='Historical replay',exact=True).click()
        replay=page.get_by_role('region',name='Historical Replay Studio',exact=True)
        await replay.get_by_role('combobox',name='Historical dataset',exact=True).select_option('BTC-complete-fixture')
        async with asyncio.timeout(20):
            while not await replay.get_by_role('button',name='Run Historical PAPER Replay',exact=True).is_enabled():await asyncio.sleep(.05)
        await replay.get_by_role('button',name='Run Historical PAPER Replay',exact=True).click()
        await replay.get_by_role('heading',name='Replay receipt',exact=True).wait_for()
        await page.get_by_role('button',name='Scenario & optimization',exact=True).click()
        await page.get_by_label('Frames',exact=True).fill('3')
        await page.get_by_role('button',name='Run Simulation',exact=True).click()
        await page.get_by_role('region',name='Completed simulation',exact=True).wait_for(timeout=60000)
        await page.get_by_role('button',name='Run Bounded Grid Search',exact=True).click()
        await page.get_by_role('region',name='Completed optimization',exact=True).wait_for(timeout=60000)
        passed('Existing historical replay, scenario simulation and bounded optimizer still run')
        # Exercise existing Vault UI, then carry its validated proposal into comparison.
        await page.evaluate("location.hash='#/vault'")
        await page.get_by_role('heading',name='Research vault & accounting',exact=True).wait_for()
        await page.get_by_label('Simulated starting capital (quote)',exact=True).fill('12345.123456789123456789')
        await page.get_by_role('button',name='Validate / Preview',exact=True).click()
        choose=page.get_by_role('button',name='Use configuration for PAPER research',exact=True)
        async with asyncio.timeout(20):
            while not await choose.is_enabled():await asyncio.sleep(.05)
        await choose.click()
        await page.evaluate("location.hash='#/simulation'")
        await page.get_by_role('button',name='Scenario vs historical',exact=True).click()
        await select();r=await run()
        assert r['request']['research']['config']['initial_equity_quote']=='12345.123456789123456789'
        assert next(x for x in r['receipt']['rows'] if x['name']=='starting_equity')['scenario']['value']=='12345.123456789123456789'
        await page.set_viewport_size({'width':390,'height':844})
        await studio.locator('.srcExact').first.focus()
        assert await studio.locator('.srcExact').first.get_attribute('aria-label')=='Exact backend value: 12345.123456789123456789 quote'
        assert await page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1')
        await shot('vault-exact-decimal-390.png')
        passed('Existing Vault preset validation, captured accounting proposal, exact long Decimal strings and keyboard-readable mobile values')
        assert not report['page_errors'],report['page_errors']
        report['unexpected_console_errors']=[e for e in report['console_errors'] if not any(token in e for token in ('WebSocket','status of 404','status of 422','status of 429','status of 503','status of 500','ERR_CONNECTION_REFUSED'))]
        assert not report['unexpected_console_errors'],report['unexpected_console_errors']
        report['classification']='PASS';await ctx.close();await browser.close()
    except Exception as exc:
        report['failure']=repr(exc)
        raise
    finally:
        for proc in processes:stop(proc)
        for log in logs:log.close()
        report['duration_seconds']=round(time.monotonic()-started,3)
        (out/'browser-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('requests','console_errors')},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--python',default=str(ROOT/'backend/.venv/bin/python'))
    p.add_argument('--chromium',default='/usr/bin/chromium');p.add_argument('--output',default=str(ROOT/'docs/acceptance/phase165c2'))
    asyncio.run(main(p.parse_args()))
