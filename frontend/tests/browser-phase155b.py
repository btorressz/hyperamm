"""Real Chromium -> production HTTP/WS -> actual observer -> fake SDK callbacks."""
import argparse,asyncio,importlib.util,json,os,signal,subprocess,time
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[2]

async def main(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True);work=ROOT/'work/browser155b';work.mkdir(parents=True,exist_ok=True)
    report={'classification':'FAIL','evidence':'DETERMINISTIC SDK FIXTURES — NOT LIVE VENUE DATA',
        'workflows':[],'page_errors':[],'screenshots':[]};started=time.monotonic()
    env={**os.environ,'MARKET_DATA_MODE':'DEMO','EXECUTION_MODE':'PAPER','ENABLE_HYPERLIQUID_TESTNET_ORDERS':'false',
        'LIVE_OBSERVATIONS_ENABLED':'false','LIVE_STREAMS_ENABLED':'false','REDIS_ENABLED':'false'}
    logs=[(work/'backend.log').open('w'),(work/'vite.log').open('w')]
    processes=[subprocess.Popen([args.python,'-m','uvicorn','phase155b_browser_backend:app','--app-dir',str(ROOT/'frontend/tests'),
        '--host','127.0.0.1','--port','8000'],cwd=ROOT/'backend',env=env,stdout=logs[0],stderr=subprocess.STDOUT,start_new_session=True),
        subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5173'],cwd=ROOT/'frontend',stdout=logs[1],stderr=subprocess.STDOUT,start_new_session=True)]
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox'])
            ctx=await browser.new_context(viewport={'width':1440,'height':900});page=await ctx.new_page();page.set_default_timeout(15000)
            page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
            async def wait_js(expression,*,arg=None):
                # Evaluate the resolved boolean explicitly: Playwright 1.64.1
                # wait_for_function treats async predicate Promises as truthy.
                async with asyncio.timeout(15):
                    while not await page.evaluate(expression,arg):await asyncio.sleep(.01)
            for _ in range(80):
                try:
                    if (await ctx.request.get('http://127.0.0.1:8000/api/v1/health')).status==200:break
                except Exception:pass
                await asyncio.sleep(.1)
            async def control(kind):
                r=await ctx.request.post('http://127.0.0.1:8000/__fixture__/phase155b',data={'kind':kind});assert r.status==200
            async def resources():return await (await ctx.request.get('http://127.0.0.1:8000/__fixture__/phase155b-resources')).json()
            async def capture(name):
                await page.evaluate('document.fonts.ready')
                await page.locator('.liveSelector').evaluate('(e)=>window.scrollTo(0,window.scrollY+e.getBoundingClientRect().top-105)')
                await page.screenshot(path=str(out/name),full_page=True);report['screenshots'].append(name)
            async def select(m):
                await page.get_by_role('button',name=f'{m}-PERP — '+{'BTC':'Bitcoin','ETH':'Ethereum','SOL':'Solana'}[m],exact=True).click()
                await wait_js("async m=>{const s=(await import('/src/stores/liveMarkets.ts')).useLiveMarketStore.getState();return s.current&&s.selectedLiveMarket===m&&s.evidence?.snapshot.market===m&&s.evidence.snapshot.status.connection_state==='CONNECTED'}",arg=m)
            await page.goto('http://127.0.0.1:5173/#/markets')
            await page.get_by_role('button',name='Live Market Intelligence',exact=True).click();await select('BTC')
            await wait_js("()=>!!document.querySelector('.liveChart canvas')")
            await page.evaluate("()=>{const e=document.createElement('div');e.textContent='DETERMINISTIC SDK FIXTURES · NOT LIVE VENUE DATA';e.style='position:fixed;bottom:0;left:0;right:0;background:#653f08;color:white;z-index:9999;padding:8px;text-align:center';document.body.appendChild(e)}")
            await capture('fixture-btc-overview-desktop.png')
            report['workflows'].append('Production observer accepts fake SDK callbacks and streams actual normalized BTC evidence to Chromium')
            await select('ETH');await capture('fixture-eth-orderbook-desktop.png')
            await select('SOL');await capture('fixture-sol-perpetual-desktop.png')
            report['workflows'].append('BTC/ETH/SOL selection isolates actual server-owned stream snapshots')
            old=(await resources())['generation'];await control('reconnect')
            await wait_js("async old=>{const s=(await import('/src/stores/liveMarkets.ts')).useLiveMarketStore.getState();return s.current&&s.connectionGeneration>old&&s.evidence?.snapshot.status.connection_state==='CONNECTED'}",arg=old)
            r=await resources();assert r['active_sdk_clients']==1 and r['retired_clients_closed'],r
            report['workflows'].append('Actual observer disconnect/reconnect retires SDK client and browser generation then resynchronizes')
            await select('BTC');await control('degraded')
            await wait_js("async()=>{const s=(await import('/src/stores/liveMarkets.ts')).useLiveMarketStore.getState();return s.evidence?.snapshot.observation_status==='DEGRADED'}")
            row=page.get_by_role('region',name='Live provider evidence',exact=True).locator('tbody tr').first
            await row.get_by_text('DEGRADED',exact=True).wait_for()
            assert 'HEALTHY' not in await row.inner_text()
            await capture('fixture-degraded-provider-desktop.png')
            r=await ctx.request.get('http://127.0.0.1:8000/api/v1/live-markets/BTC/references');health=await r.json()
            assert health['providers'][0]['status']=='DEGRADED' and health['providers'][0]['price'] is not None
            report['workflows'].append('Rejected wrong-channel callback retains evidence with DEGRADED native provider status')
            await ctx.set_offline(True)
            await wait_js("async()=>!(await import('/src/stores/liveMarkets.ts')).useLiveMarketStore.getState().current")
            await capture('fixture-disconnected-desktop.png');await ctx.set_offline(False);await control('active')
            await page.get_by_role('button',name='Retry live observation',exact=True).click();await select('BTC')
            await page.set_viewport_size({'width':390,'height':844});await capture('fixture-live-intelligence-mobile.png')
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            report['workflows'].append('Browser offline/online retires current evidence; mobile recovers without overflow')
            await page.evaluate("()=>location.hash='#/dashboard'")
            async with asyncio.timeout(5):
                while (await resources())['subscribers']:await asyncio.sleep(.01)
            report['workflows'].append('Browser navigation releases the production service subscriber')
            report['resources_after_navigation']=await resources();await ctx.close();await browser.close()
            assert not report['page_errors'];report['classification']='PASS'
    finally:
        for proc in processes:
            if proc.poll() is None:
                os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
        for log in logs:log.close()
        report['duration_seconds']=round(time.monotonic()-started,3)
        (out/'browser-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

async def legacy_regression(args):
    # Reuse every existing Phase 15.5A workflow with resolved async predicates.
    from playwright.async_api import Page
    original_wait=Page.wait_for_function
    async def resolved_wait(self,expression,*,arg=None,timeout=None,polling=None):
        if not expression.lstrip().startswith('async'):
            return await original_wait(self,expression,arg=arg,timeout=timeout,polling=polling)
        async with asyncio.timeout((timeout or 30000)/1000):
            while not await self.evaluate(expression,arg):await asyncio.sleep(.01)
        return await self.evaluate_handle(expression,arg)
    Page.wait_for_function=resolved_wait
    spec=importlib.util.spec_from_file_location('browser155a',Path(__file__).with_name('browser-phase155a.py'))
    legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
    args.url='http://127.0.0.1:5173';args.work_name='browser155b-regression';args.extra_acceptance=legacy.additional
    await legacy.base.main(args)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--python',default='python');p.add_argument('--chromium',default='/usr/bin/chromium')
    p.add_argument('--output',default=str(ROOT/'docs/acceptance/phase155b'));p.add_argument('--legacy-regression',action='store_true')
    args=p.parse_args();asyncio.run(legacy_regression(args) if args.legacy_regression else main(args))
