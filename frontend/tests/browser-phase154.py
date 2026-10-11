"""Actual Chromium assertions, real PAPER runs, normalized fixtures; no venue data."""
import argparse,asyncio,json,os,signal,subprocess,time
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[2]
SIZES=[(1920,1080),(1440,900),(1366,768),(1024,768),(768,900),(390,844)]

async def main(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    work=ROOT/'work/browser154';work.mkdir(parents=True,exist_ok=True)
    report={'fixture_notice':'DETERMINISTIC FIXTURE ACCEPTANCE — NOT LIVE VENUE DATA','workflows':[],'viewports':[],'page_errors':[],'mutations':[]}
    started=time.monotonic()
    env={**os.environ,'MARKET_DATA_MODE':'DEMO','EXECUTION_MODE':'PAPER','ENABLE_HYPERLIQUID_TESTNET_ORDERS':'false','LIVE_OBSERVATIONS_ENABLED':'false','LIVE_STREAMS_ENABLED':'false'}
    logs=[(work/'backend.log').open('w'),(work/'vite.log').open('w')]
    servers=[subprocess.Popen([args.python,'-m','uvicorn','phase154_browser_backend:app','--app-dir',str(ROOT/'frontend/tests'),'--host','127.0.0.1','--port','8000'],cwd=ROOT/'backend',env=env,stdout=logs[0],stderr=subprocess.STDOUT,start_new_session=True),
             subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5173'],cwd=ROOT/'frontend',stdout=logs[1],stderr=subprocess.STDOUT,start_new_session=True)]
    def passed(s):report['workflows'].append(s);print(s,flush=True)
    try:
      async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox'])
        ctx=await browser.new_context(viewport={'width':1440,'height':900},timezone_id='America/Los_Angeles')
        page=await ctx.new_page();page.set_default_timeout(20000)
        page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        page.on('request',lambda r:report['mutations'].append({'method':r.method,'url':r.url}) if r.method in ['POST','PUT','PATCH','DELETE'] else None)
        for _ in range(100):
            try:
                if (await ctx.request.get('http://127.0.0.1:8000/api/v1/health',timeout=500)).status==200:break
            except Exception:pass
            await asyncio.sleep(.2)
        async def control(**change):
            r=await ctx.request.post('http://127.0.0.1:8000/__fixture__/live-control',data=change);assert r.status==200,await r.text()
        async def nav(slug):await page.evaluate('(s)=>location.hash="#/"+s',slug);await page.wait_for_timeout(200)
        async def workspace():
            await nav('markets');await page.get_by_role('button',name='Market vs Research',exact=True).click()
            await page.get_by_label('Comparison observed market').wait_for()
        async def store():
            return await page.evaluate("async()=>{const s=(await import('/src/stores/marketResearchComparison.ts')).useMarketResearchComparisonStore.getState();return {results:s.results,selectedId:s.selectedId,artifact:s.artifact}}")
        async def artifact():
            for _ in range(400):
                a=(await store())['artifact']
                if a:return a
                await asyncio.sleep(.05)
            raise AssertionError(await page.locator('.marketResearchWorkspace').inner_text())
        async def capture(refresh=False):
            previous=(await store())['artifact'];previous_time=previous['data']['generated_at'] if previous else None
            await page.get_by_role('button',name='Refresh observed comparison' if refresh else 'Compare with observed market',exact=True).click()
            for _ in range(400):
                a=(await store())['artifact']
                if a and a['data']['generated_at']!=previous_time:return a
                await asyncio.sleep(.05)
            raise AssertionError(await page.locator('.marketResearchWorkspace').inner_text())
        async def run(m):
            await nav('simulation');await page.get_by_role('combobox',name='Research Perpetual Market',exact=True).select_option(m)
            await page.get_by_label('Frames',exact=True).fill('3');await page.get_by_role('button',name='Run Simulation',exact=True).click()
            await page.get_by_role('region',name='Completed simulation',exact=True).wait_for()
            rows=(await store())['results'];assert rows[0]['research']['research_market']==m
            return rows[0]['id']
        async def select(m,id):
            await page.get_by_label('Comparison observed market').select_option(m)
            await page.get_by_label('Completed PAPER result').select_option(id)
            await page.wait_for_timeout(300)
        async def authority():
            return await page.evaluate("async()=>{const t=(await import('/src/stores/terminal.ts')).useTerminalStore.getState().terminal;return {config:t.strategy.config,running:t.strategy.running,kill:t.risk.kill_switch_active,orders:t.orders,ledgerVersion:t.vault.ledger_version,ledgerFingerprint:t.vault.ledger_fingerprint,testnet:t.diagnostics.testnet_enabled}}")
        async def research():
            return await page.evaluate("async()=>{const m=(await import('/src/stores/researchMarkets.ts')).useResearchMarketStore.getState();const v=(await import('/src/stores/researchVault.ts')).useResearchVaultStore.getState();return {market:m.selectedResearchMarket,selection:m.marketSelectionVersion,epoch:m.evidenceEpoch,approved:v.approvedConfig,validated:v.lastValidatedConfig}}")
        await page.goto(args.url+'/#/markets');await page.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED')
        await workspace();assert await page.get_by_role('button',name='Compare with observed market',exact=True).is_disabled()
        passed('No completed result: comparison disabled and Simulation navigation available')
        id=await run('BTC');await workspace();await select('BTC',id)
        a=await capture();assert a['data']['comparison_status']=='UNAVAILABLE' and a['data']['research']['assumptions']['market']=='BTC'
        assert all(x['observed_value'] is None for x in a['data']['metrics'])
        assert 'Hypothetical session PnL' in await page.locator('.marketResearchWorkspace').inner_text()
        passed('Real BTC PAPER run with live switches disabled: assumptions and performance survive; observed unavailable')
        await control(kind='active');await nav('simulation');await workspace();await select('BTC',id)
        await page.evaluate("()=>{const b=document.createElement('div');b.id='fixture-notice';b.textContent='DETERMINISTIC FIXTURE ACCEPTANCE — NOT LIVE VENUE DATA';b.style='position:fixed;bottom:0;left:0;right:0;background:#653f08;color:white;z-index:9999;padding:8px;text-align:center;font:12px sans-serif';document.body.appendChild(b)}")
        before=await authority();before_research=await research();a=await capture(refresh=True)
        metrics={x['metric_name']:x for x in a['data']['metrics']}
        assert a['historicalReason'] is None, a['historicalReason']
        assert metrics['midpoint']['absolute_difference'] is not None and metrics['funding_rate']['comparison_status']=='PARTIAL'
        assert metrics['bid_depth_base']['absolute_difference'] is not None
        await page.locator('.marketResearchWorkspace').evaluate('(e)=>window.scrollTo(0,window.scrollY+e.getBoundingClientRect().top-100)')
        await page.screenshot(path=str(out/'btc-comparison-1440.png'))
        passed('BTC explicit capture shows actual Decimal price/spread/funding/book differences and independent source timestamps')
        original=a['data'];await control(action='publish');await page.wait_for_timeout(250)
        assert (await artifact())['data']==original
        passed('New live publication never silently recalculates frozen comparison')
        await control(kind='stale_context',action='publish');a=await capture(refresh=True);metrics={x['metric_name']:x for x in a['data']['metrics']}
        assert metrics['midpoint']['absolute_difference'] is not None and metrics['mark_price']['absolute_difference'] is None and metrics['funding_rate']['absolute_difference'] is None
        assert a['data']['observed']['acquisition_gap_seconds']>50
        passed('Stale context and fresh L2: price/spread remain eligible while mark/funding are unavailable')
        await control(kind='missing_depth',action='publish');a=await capture(refresh=True);assert next(x for x in a['data']['metrics'] if x['metric_name']=='bid_depth_base')['absolute_difference'] is None
        passed('Insufficient visible levels: unavailable numerical depth comparison without invented liquidity')
        await page.get_by_label('Comparison observed market').select_option('ETH');await page.wait_for_timeout(300)
        assert (await artifact())['data']['research']['research_market']=='BTC' and (await artifact())['historicalReason']
        a=await capture(refresh=True);assert a['data']['comparison_status']=='NOT_COMPARABLE' and all(x['absolute_difference'] is None for x in a['data']['metrics'])
        assert await authority()==before and await research()==before_research
        passed('ETH selection keeps BTC research identity, retires historical artifact and blocks cross-asset deltas; authority unchanged')
        for m in ['ETH','SOL']:
            await control(kind='active');rid=await run(m);await workspace();await select(m,rid);a=await capture()
            assert a['data']['market']==m and a['data']['research']['research_market']==m
            assert next(x for x in a['data']['metrics'] if x['metric_name']=='midpoint')['absolute_difference'] is not None
            if m=='SOL':assert next(x for x in a['data']['metrics'] if x['metric_name']=='bid_depth_base')['absolute_difference'] is None
            passed(f'{m} real PAPER result explicitly selected with matching normalized observations')
        before=await authority();before_research=await research();frozen=(await artifact())['data']
        await nav('vault');await workspace();assert (await artifact())['historicalReason'] and (await artifact())['data']==frozen
        passed('Navigation retains bounded historical comparison; no implicit capture or research mutation')
        delayed,release=asyncio.Event(),asyncio.Event()
        async def delay(route):
            actual=await route.fetch();delayed.set();await release.wait()
            try:await route.fulfill(response=actual)
            except Exception:pass
        await page.route('**/research-market-comparison/compare',delay)
        await page.get_by_role('button',name='Refresh observed comparison',exact=True).click();await asyncio.wait_for(delayed.wait(),5)
        await control(observer='00000000-0000-0000-0000-000000000154',generation=2,action='publish')
        await page.wait_for_timeout(300);release.set();await page.wait_for_timeout(400);await page.unroute('**/research-market-comparison/compare',delay)
        assert (await artifact())['data']==frozen and (await artifact())['historicalReason']
        passed('Observer restart during delayed POST retires completion; prior artifact stays historical')
        await page.wait_for_timeout(400);a=await capture(refresh=True)
        assert a['data']['provenance']['observer_instance_id']=='00000000-0000-0000-0000-000000000154'
        passed('Explicit refresh captures new observer/generation after resynchronization')
        assert a['historicalReason'] is None, a['historicalReason']
        economic=a['data']
        await page.wait_for_timeout(11000)
        await control(action='publish');await page.wait_for_timeout(200)
        assert (await artifact())['historicalReason'] and 'expired' in (await artifact())['historicalReason']
        assert (await artifact())['data']==economic
        passed('Captured freshness expires despite a newer live publication; economic artifact is unchanged and historical')
        # Missing assumptions fixture retains an actual completed result's identity/performance.
        await page.evaluate("async()=>{const s=(await import('/src/stores/marketResearchComparison.ts')).useMarketResearchComparisonStore;const x=structuredClone(s.getState().results.find(r=>r.id===s.getState().selectedId));x.research.assumptions=null;s.setState({results:[x],selectedId:x.id,version:s.getState().version+1})}")
        a=await capture(refresh=True);assert a['data']['comparison_status']=='UNAVAILABLE' and a['data']['research']['assumptions'] is None
        assert 'Research assumption detail unavailable for this prior result' in await page.locator('.marketResearchWorkspace').inner_text()
        passed('Legacy completed result: hypothetical performance retained, missing assumptions explained without synthesized controls')
        for w,h in SIZES:
            await page.set_viewport_size({'width':w,'height':h});await page.wait_for_timeout(180)
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),f'overflow {w}'
            assert await page.get_by_label('Comparison observed market').is_visible()
            assert await page.get_by_role('button',name='Refresh observed comparison',exact=True).is_visible()
            report['viewports'].append({'width':w,'height':h,'overflow':False})
            if w in (1440,390):
                await page.locator('.marketResearchWorkspace').evaluate('(e)=>window.scrollTo(0,window.scrollY+e.getBoundingClientRect().top-100)')
                await page.screenshot(path=str(out/f'comparison-{w}.png'))
        assert await authority()==before and await research()==before_research
        assert all('/simulation/run' in r['url'] or '/research-market-comparison/compare' in r['url'] for r in report['mutations'])
        assert sum('/simulation/run' in r['url'] for r in report['mutations'])==3
        assert not report['page_errors'],report['page_errors']
        passed('Six responsive viewports, zero document overflow/page exceptions; only three explicit PAPER runs and comparison POSTs')
        await browser.close()
    finally:
        for proc in servers:
            if proc.poll() is None:
                os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=10)
        for log in logs:log.close()
        report['elapsed_seconds']=round(time.monotonic()-started,2)
        (out/'browser-results.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--python',default='python');parser.add_argument('--chromium',default='/usr/bin/chromium');parser.add_argument('--url',default='http://127.0.0.1:5173');parser.add_argument('--output',default=str(ROOT/'docs/acceptance/phase154'))
    asyncio.run(main(parser.parse_args()))
