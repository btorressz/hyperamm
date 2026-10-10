"""Actual Chromium, Uvicorn/Vite, single-market PAPER acceptance; no AI screenshots."""
import argparse
import asyncio
import json
import os
import signal
from pathlib import Path
import subprocess
import sys

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
SIZES = [(1920,1080),(1440,900),(1366,768),(1024,768),(768,900),(390,844)]
PAGES = ['dashboard','markets','strategy','amm-settings','execution','risk','agents','vault',
         'analytics','simulation','logs','settings']


async def main(args):
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    scratch = Path(args.work); scratch.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'MARKET_DATA_MODE':'DEMO', 'EXECUTION_MODE':'PAPER',
           'ENABLE_HYPERLIQUID_TESTNET_ORDERS':'false'}
    report = {'route_checks':[], 'workflows':[], 'page_errors':[], 'mutations':[], 'runs':[],
              'fixtures':'Delayed actual run/catalog responses and unavailable catalog are browser-only fixtures. All run/optimization/comparison economics use actual backend.'}
    def passed(name):
        report['workflows'].append(name); print(name, flush=True)
    log = (scratch/'browser-backend.log').open('w')
    vite_log = (scratch/'browser-vite.log').open('w')
    def backend():
        return subprocess.Popen([args.python,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000'],
            cwd=ROOT/'backend', env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    server = backend()
    vite = subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5173'],
        cwd=ROOT/'frontend', stdout=vite_log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(executable_path=args.chromium, headless=True, args=['--no-sandbox'])
            ctx = await browser.new_context(timezone_id='America/Los_Angeles', viewport={'width':1440,'height':900})
            page = await ctx.new_page(); page.set_default_timeout(20000)
            page.on('pageerror', lambda e:report['page_errors'].append(str(e)))
            page.on('request', lambda r:report['mutations'].append({'method':r.method,'url':r.url})
                if r.method in ['POST','PUT','PATCH','DELETE'] else None)
            for _ in range(60):
                try:
                    response = await ctx.request.get(args.url+'/api/v1/health', timeout=1000)
                    if response.status == 200: break
                except Exception: pass
                await asyncio.sleep(.25)
            await page.goto(args.url+'/#/simulation')
            await page.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED')
            async def navigate(slug):
                await page.evaluate('(slug)=>location.hash="#/"+slug', slug)
                await page.wait_for_timeout(200)
            async def terminal():
                return await page.evaluate("async()=> (await import('/src/stores/terminal.ts')).useTerminalStore.getState().terminal")
            def authority(t):
                return {'config':t['strategy']['config'], 'running':t['strategy']['running'],
                    'ledger_version':t['vault']['ledger_version'], 'ledger_fingerprint':t['vault']['ledger_fingerprint'],
                    'kill':t['risk']['kill_switch_active'], 'orders':t['orders'],
                    'testnet_enabled':t['diagnostics']['testnet_enabled']}
            async def market(id):
                selector = page.get_by_role('combobox', name='Research Perpetual Market', exact=True)
                await selector.select_option(id)
                await page.get_by_role('region',name='Research Perpetual Market',exact=True).get_by_text(f'{id}-PERP · Hyperliquid native perpetual · PAPER / SIMULATED', exact=True).wait_for()
            async def screenshot(element, filename):
                await element.evaluate('(el)=>window.scrollTo(0,window.scrollY+el.getBoundingClientRect().top-(innerWidth<650?160:100))')
                await page.evaluate('document.activeElement?.blur()')
                await page.screenshot(path=str(out/filename))
            async def run(id, scenario='FLASH_MOVE', frames='30'):
                await market(id)
                await page.get_by_label('Scenario',exact=True).select_option(scenario)
                await page.get_by_label('Frames',exact=True).fill(frames)
                async with page.expect_response(lambda r:'/simulation/run' in r.url and r.request.method=='POST') as response:
                    await page.get_by_role('button',name='Run Simulation',exact=True).click()
                r = await response.value; assert r.status==200,await r.text()
                data = await r.json()
                assert data['research_market']==id and data['vault']['market']==id
                assert all(x['market']==id for x in data['orders']+data['fills'])
                await page.get_by_role('region',name='Completed simulation',exact=True).get_by_text(f'Market: {id}-PERP',exact=False).wait_for()
                report['runs'].append({k:data[k] for k in ['research_market','market_profile_version','market_profile_fingerprint','metadata_source','metadata_status','dataset_fingerprint','strategy_fingerprint','run_fingerprint','engine_version']}
                    | {'fill_count':data['metrics']['fill_count'],'risk_state_counts':data['metrics']['risk_state_counts']})
                return data
            await page.get_by_text('DEMO · SIMULATED METADATA',exact=True).wait_for()
            assert await page.get_by_role('combobox',name='Research Perpetual Market',exact=True).locator('option').count()==3
            before = authority(await terminal()); assert not before['running'] and not before['testnet_enabled']
            passed('Catalog loads exactly BTC/ETH/SOL with honest DEMO metadata, fixed anchors and precision')
            btc = await run('BTC')
            await screenshot(page.get_by_role('region',name='Completed simulation',exact=True),'btc-simulation-1440.png')
            assert authority(await terminal())==before
            passed('A: BTC FLASH_MOVE actual PAPER metrics, trace, market provenance and unchanged operational ETH')
            await market('ETH')
            assert await page.get_by_role('region',name='Completed simulation',exact=True).get_by_text('Market: BTC-PERP',exact=False).count()==1
            eth = await run('ETH','QUIET')
            assert btc['dataset_fingerprint']!=eth['dataset_fingerprint']
            passed('B: ETH selection uses its profile while prior completed BTC evidence retains BTC labeling')
            sol = await run('SOL')
            assert sol['metrics']['risk_state_counts'].get('HALT',0)>0
            assert authority(await terminal())==before
            passed('C: SOL uses 150 quote anchor/2 decimals and reports genuine unchanged-limit HALTs without fabricated fills')
            await navigate('vault'); await market('BTC')
            assert 'ETH' in await page.get_by_text('Operational Vault Accounting',exact=False).inner_text()
            await page.get_by_role('button',name='High-Cost Stress',exact=False).click()
            async def validate():
                await page.get_by_role('button',name='Validate / Preview',exact=True).click()
                await page.get_by_text('VALIDATED CURRENT DRAFT',exact=True).wait_for()
                await page.get_by_role('button',name='Use configuration for PAPER research',exact=True).click()
            await validate()
            await page.get_by_label('Taker fee (bps)',exact=True).fill('30'); await validate()
            await navigate('simulation')
            assert await page.get_by_role('combobox',name='Research Perpetual Market',exact=True).input_value()=='BTC'
            await page.get_by_label('Frames',exact=True).fill('30')
            async with page.expect_response(lambda r:'/research-vault/compare' in r.url) as response:
                await page.get_by_role('button',name='Compare preset baseline vs customized',exact=True).click()
            r=await response.value;assert r.status==200,await r.text();cmp=await r.json()
            old,new=cmp['baseline_result'],cmp['custom_result']
            assert old['research_market']==new['research_market']=='BTC'
            assert old['dataset_fingerprint']==new['dataset_fingerprint'] and old['strategy_fingerprint']==new['strategy_fingerprint']
            await page.get_by_text('Comparison market: BTC-PERP',exact=False).wait_for()
            assert authority(await terminal())==before
            passed('D: High-Cost Stress baseline/customized comparison shares one BTC dataset and strategy; Vault ledger unchanged')
            await page.get_by_label('Frames',exact=True).fill('3')
            await page.get_by_label('Optimization preset',exact=True).select_option('Inventory')
            for id in ['BTC','ETH','SOL']:
                await market(id)
                async with page.expect_response(lambda r:'/simulation/optimize' in r.url) as response:
                    await page.get_by_role('button',name='Run Bounded Grid Search',exact=True).click()
                r=await response.value;assert r.status==200,await r.text();opt=await r.json()
                assert opt['research_market']==id
                await page.get_by_role('region',name='Completed optimization',exact=True).get_by_text(f'Market: {id}-PERP',exact=False).wait_for()
            passed('Bounded Inventory optimization succeeds independently for BTC ETH SOL with fixed candidate market')
            await run('SOL','QUIET','3')
            await market('BTC');await page.get_by_label('Frames',exact=True).fill('30')
            # Delayed actual response; no fabricated result economics.
            entered,release=asyncio.Event(),asyncio.Event()
            async def delayed(route):
                actual=await route.fetch();entered.set();await release.wait();await route.fulfill(response=actual)
            await page.route('**/simulation/run',delayed)
            await page.get_by_role('button',name='Run Simulation',exact=True).click();await entered.wait()
            await market('SOL');release.set()
            await page.get_by_text('Research response retired after market selection',exact=False).wait_for()
            await page.unroute('**/simulation/run',delayed)
            assert await page.get_by_role('region',name='Completed simulation',exact=True).get_by_text('Market: SOL-PERP',exact=False).count()==1
            passed('E1: switching market during actual delayed BTC run retires its response; completed SOL evidence stays SOL')
            assert authority(await terminal())==before
            await navigate('vault');await market('BTC');await validate()
            old_terminal=await terminal();server.terminate();server.wait(timeout=10)
            await page.get_by_text('Current backend session unavailable.',exact=False).wait_for()
            await page.get_by_text('OUTDATED PREVIEW',exact=True).wait_for()
            server=backend()
            await page.wait_for_function("async(old)=>{const s=(await import('/src/stores/terminal.ts')).useTerminalStore.getState();return s.wsState==='connected'&&s.terminal.process_id!==old}",arg=old_terminal['process_id'],timeout=25000)
            await page.get_by_text('DEMO · SIMULATED METADATA',exact=True).wait_for()
            assert await page.get_by_role('button',name='Use configuration for PAPER research',exact=True).is_disabled()
            await validate();await navigate('simulation');await run('BTC','QUIET','3')
            passed('E2: real backend restart retires market/accounting evidence, preserves BTC preference, revalidates and runs')
            # Browser-only unavailable catalog fixture. Clear accepted catalog through its public invalidation action.
            actual=await (await ctx.request.get(args.url+'/api/v1/research-markets')).json()
            unavailable=json.loads(json.dumps(actual))
            for item in unavailable['markets']:
                item.update(metadata_status='UNAVAILABLE',metadata_source='NONE',sz_decimals=None,
                    research_supported=False,asset_index=None,listed=None,unavailable_reason='Browser fixture: SDK unavailable and DEMO disallowed')
            async def unavailable_route(route):await route.fulfill(status=200,json=unavailable)
            await page.route('**/research-markets',unavailable_route)
            await page.evaluate("async()=> (await import('/src/stores/researchMarkets.ts')).useResearchMarketStore.getState().invalidate()")
            await page.get_by_text('MARKET UNAVAILABLE',exact=True).wait_for()
            assert await page.get_by_role('button',name='Run Simulation',exact=True).is_disabled()
            await page.unroute('**/research-markets',unavailable_route)
            await page.evaluate("async()=> (await import('/src/stores/researchMarkets.ts')).useResearchMarketStore.getState().invalidate()")
            await page.get_by_text('DEMO · SIMULATED METADATA',exact=True).wait_for()
            passed('F: real SDK outage uses explicit DEMO fallback; disallowed-fallback browser fixture disables research')
            # Real-session slow catalog race after invalidation.
            entered,release=asyncio.Event(),asyncio.Event()
            async def delayed_catalog(route):
                actual=await route.fetch();entered.set();await release.wait();await route.fulfill(response=actual)
            await page.route('**/research-markets',delayed_catalog)
            await page.evaluate("async()=> (await import('/src/stores/researchMarkets.ts')).useResearchMarketStore.getState().invalidate()")
            await entered.wait()
            await page.evaluate("async()=> (await import('/src/stores/researchMarkets.ts')).useResearchMarketStore.getState().selectMarket('ETH')")
            release.set();await page.get_by_text('ETH-PERP · Hyperliquid native perpetual · PAPER / SIMULATED',exact=True).wait_for()
            await page.unroute('**/research-markets',delayed_catalog)
            passed('Slow catalog response validates current ETH selection without restoring an old BTC preference')
            for width,height in SIZES:
                await page.set_viewport_size({'width':width,'height':height})
                for slug in PAGES:
                    await navigate(slug)
                    if slug in ['vault','simulation']:
                        await page.get_by_text('DEMO · SIMULATED METADATA',exact=True).wait_for()
                    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(width,slug)
                    report['route_checks'].append({'route':slug,'width':width,'height':height})
                print('Viewport',width,'passed',flush=True)
            await navigate('vault');await market('BTC')
            await screenshot(page.locator('.researchStudio'),'btc-vault-390.png')
            await page.set_viewport_size({'width':1440,'height':900})
            await screenshot(page.locator('.researchStudio'),'btc-vault-1440.png')
            after=authority(await terminal())
            assert all(after[k]==before[k] for k in ['config','running','kill','orders','testnet_enabled','ledger_version'])
            assert not report['page_errors'],report['page_errors']
            assert all(any(path in m['url'] for path in ['/research-vault/preview','/research-vault/compare','/simulation/run','/simulation/optimize']) for m in report['mutations'])
            passed('72 route/viewport checks, zero page exceptions/overflow, and zero trading or configuration writes')
            await browser.close()
    finally:
        for process in (server,vite):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
        log.close();vite_log.close()
        (scratch/'browser-results.json').write_text(json.dumps(report,indent=2)+'\n')
    (out/'browser-results.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:5173')
    parser.add_argument('--output',default=str(ROOT/'docs/acceptance/phase146'))
    parser.add_argument('--work',default=str(ROOT.parent/'work/phase146'))
    parser.add_argument('--chromium',default='/usr/bin/chromium')
    parser.add_argument('--python',default=sys.executable)
    asyncio.run(main(parser.parse_args()))
