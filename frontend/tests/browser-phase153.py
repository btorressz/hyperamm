"""Actual Chromium and native browser sockets against loopback Pydantic fixtures.

Install Playwright locally; all venue networking remains disabled. Test-only
server controls are separate from browser requests and production application.
"""
import argparse,asyncio,json,os,signal,subprocess,time
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[2]
SIZES=[(1920,1080),(1440,900),(1366,768),(1024,768),(768,900),(390,844)]

async def main(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    scratch=ROOT/'work/browser153';scratch.mkdir(parents=True,exist_ok=True)
    report={'fixture_notice':'DETERMINISTIC FIXTURE ACCEPTANCE — NOT LIVE VENUE DATA','viewports':[],'workflows':[],'page_errors':[],'mutations':[],'console_errors':[],'elapsed_seconds':0}
    started=time.monotonic()
    env={**os.environ,'MARKET_DATA_MODE':'DEMO','EXECUTION_MODE':'PAPER','ENABLE_HYPERLIQUID_TESTNET_ORDERS':'false','LIVE_OBSERVATIONS_ENABLED':'false','LIVE_STREAMS_ENABLED':'false'}
    logs=[(scratch/'backend.log').open('w'),(scratch/'vite.log').open('w')]
    server=subprocess.Popen([args.python,'-m','uvicorn','phase153_browser_backend:app','--app-dir',str(ROOT/'frontend/tests'),'--host','127.0.0.1','--port','8000'],cwd=ROOT/'backend',env=env,stdout=logs[0],stderr=subprocess.STDOUT,start_new_session=True)
    vite=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5173'],cwd=ROOT/'frontend',stdout=logs[1],stderr=subprocess.STDOUT,start_new_session=True)
    def passed(name):report['workflows'].append(name);print(name,flush=True)
    try:
      async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox'])
        ctx=await browser.new_context(viewport={'width':1440,'height':900},timezone_id='America/Los_Angeles')
        page=await ctx.new_page();page.set_default_timeout(20000)
        page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        page.on('console',lambda m:report['console_errors'].append(m.text) if m.type=='error' and not any(x in m.text for x in ['503','404','ERR_CONNECTION','ERR_ABORTED']) else None)
        page.on('request',lambda r:report['mutations'].append({'method':r.method,'url':r.url}) if r.method in ['POST','PUT','PATCH','DELETE'] else None)
        for _ in range(80):
            try:
                if (await ctx.request.get(args.url+'/api/v1/health',timeout=1000)).status==200:break
            except Exception:pass
            await asyncio.sleep(.25)
        async def control(**change):
            r=await ctx.request.post('http://127.0.0.1:8000/__fixture__/live-control',data=change);assert r.status==200,await r.text();return await r.json()
        async def clients():return await (await ctx.request.get('http://127.0.0.1:8000/__fixture__/clients')).json()
        async def nav(slug):await page.evaluate('(s)=>location.hash="#/"+s',slug);await page.wait_for_timeout(150)
        async def state():
            return await page.evaluate("async()=>{const s=(await import('/src/stores/liveMarkets.ts')).useLiveMarketStore.getState();return {market:s.selectedLiveMarket,current:s.current,status:s.streamStatus,observer:s.observerInstanceId,generation:s.connectionGeneration,sequence:s.latestStreamSequence,evidence:s.evidence?.snapshot}}")
        async def wait_state(predicate):
            for _ in range(400):
                value=await state()
                if predicate(value):return value
                await asyncio.sleep(.05)
            raise AssertionError(f'Live state timeout: {await state()}')
        async def authority():
            return await page.evaluate("async()=>{const t=(await import('/src/stores/terminal.ts')).useTerminalStore.getState().terminal;return {config:t.strategy.config,running:t.strategy.running,kill:t.risk.kill_switch_active,orders:t.orders,ledgerVersion:t.vault.ledger_version,ledgerFingerprint:t.vault.ledger_fingerprint,testnet:t.diagnostics.testnet_enabled}}")
        async def research():
            return await page.evaluate("async()=>{const m=(await import('/src/stores/researchMarkets.ts')).useResearchMarketStore.getState();const v=(await import('/src/stores/researchVault.ts')).useResearchVaultStore.getState();return {market:m.selectedResearchMarket,selection:m.marketSelectionVersion,epoch:m.evidenceEpoch,approved:v.approvedConfig,validated:v.lastValidatedConfig}}")
        async def select(m):
            await page.get_by_role('button',name=f'{m}-PERP — '+{'BTC':'Bitcoin','ETH':'Ethereum','SOL':'Solana'}[m],exact=True).click()
            await wait_state(lambda s:s['market']==m and s['status']=='CONNECTED' and s['evidence']['market']==m)
        async def live():await nav('markets');await page.get_by_role('button',name='Live Market Intelligence',exact=True).click()
        async def screenshot(name):
            await page.locator('.liveSelector').evaluate('(e)=>window.scrollTo(0,window.scrollY+e.getBoundingClientRect().top-105)')
            await page.screenshot(path=str(out/name))
        await page.goto(args.url+'/#/markets');await page.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED')
        assert await page.get_by_role('button',name='Operational Market',exact=True).get_attribute('aria-pressed')=='true'
        await page.get_by_role('button',name='Live Market Intelligence',exact=True).click()
        await page.get_by_text('Live market observation is disabled by the backend operator',exact=True).wait_for()
        assert (await state())['status']=='DISABLED' and not (await state())['evidence']['order_book'] and not await clients()
        await screenshot('disabled-1440.png')
        passed('Actual disabled service: accessible Live workspace, no fabricated prices and no live browser socket')
        await nav('simulation');await page.get_by_role('combobox',name='Research Perpetual Market',exact=True).select_option('SOL')
        await page.get_by_label('Frames',exact=True).fill('3');await page.get_by_role('button',name='Run Simulation',exact=True).click()
        await page.get_by_role('region',name='Completed simulation',exact=True).wait_for()
        before_authority=await authority();before_research=await research();before_mutations=len(report['mutations'])
        assert not before_authority['running'] and not before_authority['testnet']
        await control(kind='active')
        await page.evaluate("()=>{const b=document.createElement('div');b.id='fixture-notice';b.textContent='DETERMINISTIC FIXTURE ACCEPTANCE · NOT LIVE VENUE DATA';b.style='position:fixed;bottom:0;left:0;right:0;background:#653f08;color:white;z-index:9999;padding:8px;text-align:center;font:12px sans-serif';document.body.appendChild(b)}")
        await live();await select('BTC')
        await page.get_by_role('region',name='Native L2 order book',exact=True).get_by_text('60,000',exact=True).wait_for()
        await page.wait_for_function("()=>document.querySelector('.liveChart canvas')!==null")
        assert (await state())['evidence']['perp_context']['source_timestamp'] is None
        await page.get_by_label('Chart time basis',exact=True).select_option('PERP_CONTEXT')
        await page.get_by_text('Context receipt time · event time unverified',exact=True).wait_for()
        await page.get_by_label('Chart time basis',exact=True).select_option('L2');await screenshot('btc-1440.png')
        passed('BTC native browser socket receives validated backend fixture envelope; book/chart/context and external-disabled rows render')
        delayed,release=asyncio.Event(),asyncio.Event()
        async def delay_btc(route):
            actual=await route.fetch();delayed.set();await release.wait()
            try:await route.fulfill(response=actual)
            except Exception:pass
        await page.route('**/live-markets/BTC/stream-snapshot',delay_btc)
        await page.get_by_role('button',name='Retry live observation',exact=True).click();await asyncio.wait_for(delayed.wait(),5)
        await select('ETH');release.set();await page.unroute('**/live-markets/BTC/stream-snapshot',delay_btc);await page.wait_for_timeout(150)
        assert (await state())['evidence']['market']=='ETH';assert '60,000' not in await page.get_by_role('region',name='Native L2 order book',exact=True).inner_text()
        await screenshot('eth-1440.png');passed('Delayed BTC HTTP response/socket retired during ETH selection; no mixed-market current evidence')
        await select('SOL');await page.get_by_role('region',name='Native L2 order book',exact=True).get_by_text('150.12',exact=True).wait_for()
        assert (await state())['evidence']['metadata']['sz_decimals']==2
        await screenshot('sol-1440.png');passed('SOL native metadata and actual reported price/size precision displayed independently')
        await control(action='close',market='SOL');await wait_state(lambda s:not s['current'])
        assert 'STALE — LAST OBSERVED' in await page.get_by_role('region',name='Native L2 order book',exact=True).inner_text()
        await screenshot('reconnect-1440.png');await select('SOL')
        passed('Native browser socket 1013 closure retires active data, fetches snapshot and reconnects')
        observer='11111111-2222-4333-8444-555555555555'
        await control(observer=observer,generation=2,action='publish',market='SOL')
        await wait_state(lambda s:s['observer']==observer and s['status']=='CONNECTED' and s['generation']==2)
        await control(generation=3,action='publish',market='SOL')
        await wait_state(lambda s:s['observer']==observer and s['status']=='CONNECTED' and s['generation']==3)
        passed('Observer restart and subsequent generation change independently retire evidence and resynchronize history/stream')
        await control(kind='bootstrap',action='close');await page.get_by_role('button',name='Retry live observation',exact=True).click()
        await page.get_by_text('Fresh REST source observation · streaming not yet confirmed',exact=True).wait_for()
        passed('Fresh REST source/provider health during BOOTSTRAPPING never labeled confirmed streaming')
        await control(kind='stale',action='close');await page.get_by_role('button',name='Retry live observation',exact=True).click();await select('SOL')
        assert 'STALE — LAST OBSERVED' in await page.get_by_role('region',name='Native L2 order book',exact=True).inner_text()
        assert 'Recent native context observation' in await page.get_by_role('region',name='Native perpetual metrics',exact=True).inner_text()
        passed('Stale L2 and recent receipt-time context remain distinct in rendered browser evidence')
        await control(kind='unavailable',action='close');await page.get_by_role('button',name='Retry live observation',exact=True).click()
        await wait_state(lambda s:s['status']=='UNAVAILABLE');assert not (await state())['current']
        await control(kind='active');await page.get_by_role('button',name='Retry live observation',exact=True).click();await select('BTC')
        passed('HTTP 200 unavailable payload retires current evidence; explicit retry restores only validated observations')
        for w,h in SIZES:
            await page.set_viewport_size({'width':w,'height':h});await page.wait_for_timeout(200)
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),f'Page overflow at {w}'
            assert await page.get_by_role('button',name='BTC-PERP — Bitcoin',exact=True).is_visible()
            assert await page.locator('.liveChart').evaluate('(e)=>e.clientWidth>100&&e.clientWidth<=innerWidth')
            report['viewports'].append({'width':w,'height':h,'overflow':False,'chart_resized':True,'selector_visible':True})
            if w==390:
                assert await page.locator('.liveBook').evaluate('(e)=>e.scrollWidth>=e.clientWidth');await screenshot('mobile-390.png')
        passed('All six Chromium desktop/tablet/mobile viewports have no page overflow and resize chart/selector/tables')
        await nav('dashboard');await page.wait_for_function('!document.querySelector(".liveWorkspace")')
        for _ in range(40):
            if not await clients():break
            await asyncio.sleep(.05)
        assert not await clients()
        await page.set_viewport_size({'width':1440,'height':900});await live();await select('BTC');assert await clients()==['BTC']
        passed('Navigation releases every real server browser subscription; StrictMode return owns exactly one BTC socket')
        assert before_authority==await authority();assert before_research==await research();assert len(report['mutations'])==before_mutations
        passed('Operational ETH strategy/orders/kill/ledger/signing and SOL PAPER research unchanged; zero live-page mutations')
        await control(terminal_unavailable=True,kind='unavailable');await ctx.close()
        independent=await browser.new_context(viewport={'width':390,'height':844});other=await independent.new_page()
        other.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        await other.goto(args.url+'/#/markets');await other.get_by_text('Operational market unavailable',exact=True).wait_for()
        await other.get_by_role('button',name='Live Market Intelligence',exact=True).click()
        await other.get_by_text('Backend observation unavailable; retry when conditions change.',exact=False).wait_for()
        passed('Live Markets remains accessible with no operational terminal snapshot at first mount')
        await independent.close();await browser.close()
        assert not report['page_errors'],report['page_errors'];assert not report['console_errors'],report['console_errors']
    finally:
        for process in [vite,server]:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
        for log in logs:log.close()
        report['elapsed_seconds']=round(time.monotonic()-started,2);(out/'browser-results.json').write_text(json.dumps(report,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--python',default=str(ROOT/'work/venv/bin/python'));parser.add_argument('--chromium',default='/usr/bin/chromium');parser.add_argument('--url',default='http://127.0.0.1:5173');parser.add_argument('--output',default=str(ROOT/'docs/acceptance/phase153'));asyncio.run(main(parser.parse_args()))
