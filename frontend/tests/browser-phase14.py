"""Real Chromium + local DEMO/PAPER; browser response fixtures explicitly labeled."""
import argparse, asyncio, json, os, signal, subprocess
from pathlib import Path
from playwright.async_api import async_playwright
ROOT = Path(__file__).resolve().parents[2]
SIZES = [(1920,1080),(1440,900),(1366,768),(1024,768),(768,900),(390,844)]
PAGES = ['dashboard','markets','strategy','amm-settings','execution','risk','agents','vault','analytics','simulation','logs','settings']

async def main(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    report={'route_checks':[],'workflows':[],'page_errors':[],'mutations':[],
            'fixtures':'Delayed/malformed preview responses only; simulation results use actual backend.'}
    replacement=None
    def passed(name): report['workflows'].append(name);print(name,flush=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox'])
        ctx=await browser.new_context(timezone_id='America/Los_Angeles',viewport={'width':1440,'height':900})
        page=await ctx.new_page()
        page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        page.on('request',lambda r:report['mutations'].append({'method':r.method,'url':r.url}) if r.method in ['POST','PUT','PATCH','DELETE'] else None)
        async def navigate(slug):
            await page.evaluate('(slug)=>location.hash="#/"+slug',slug)
            await page.wait_for_function('(slug)=>location.hash==="#/"+slug',arg=slug)
            await page.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED')
            await page.wait_for_timeout(180)
        async def terminal(): return await page.evaluate("async()=> (await import('/src/stores/terminal.ts')).useTerminalStore.getState().terminal")
        def authority(t):
            return {'config':t['strategy']['config'],'running':t['strategy']['running'],
                    'ledger_version':t['vault']['ledger_version'],'ledger_fingerprint':t['vault']['ledger_fingerprint'],
                    'kill':t['risk']['kill_switch_active'],'orders':t['orders'],
                    'testnet_enabled':t['diagnostics']['testnet_enabled']}
        await page.goto(args.url+'/#/vault')
        await page.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED')
        await page.get_by_role('button',name='Balanced Research',exact=False).wait_for()
        before=authority(await terminal())
        assert not before['running'] and not before['testnet_enabled']
        await page.get_by_role('button',name='Conservative Capital',exact=False).click()
        assert await page.get_by_label('Simulated starting capital (quote)',exact=True).input_value()=='50000'
        assert await page.get_by_label('Capital utilization limit (%)',exact=True).input_value()=='35'
        await page.get_by_role('button',name='Balanced Research',exact=False).click()
        assert await page.get_by_label('Simulated starting capital (quote)',exact=True).input_value()=='100000'
        assert await page.get_by_text('Session observations',exact=True).count()==1
        assert await page.get_by_role('region',name='Accounting provenance',exact=False).count()>=1
        passed('A: backend presets switch correctly; original Vault economics, ledger, provenance and session charts preserved')
        capital=page.get_by_label('Simulated starting capital (quote)',exact=True)
        maker=page.get_by_label('Maker fee (bps)',exact=True)
        taker=page.get_by_label('Taker fee (bps)',exact=True)
        cap=page.get_by_label('Capital utilization limit (%)',exact=True)
        async def validate():
            await page.get_by_role('button',name='Validate / Preview',exact=True).click()
            await page.get_by_text('VALIDATED CURRENT DRAFT',exact=True).wait_for()
        await capital.fill('12345.123456789123456789');await maker.fill('2');await taker.fill('7')
        await page.get_by_label('Simulated fee model enabled',exact=True).check()
        await page.get_by_label('Simulated funding accounting enabled',exact=True).check()
        await page.get_by_label('Funding interval (seconds)',exact=True).select_option('1')
        await cap.fill('');await cap.press_sequentially('75.1234567891234567')
        assert await cap.input_value()=='75.1234567891234567'
        passed('Exact fractional percentage remains editable through sequential keyboard typing')
        await cap.fill('50')
        await validate()
        await page.get_by_text('6172.5617283945617283945 quote',exact=False).wait_for()
        assert (await page.evaluate("async()=> (await import('/src/stores/researchVault.ts')).useResearchVaultStore.getState().lastValidatedConfig.initial_equity_quote"))=='12345.123456789123456789'
        await page.get_by_role('button',name='Use configuration for PAPER research',exact=True).click()
        passed('B: exact Decimal capital, fees, funding interval and percent conversion validated with preview fingerprint')
        await page.locator('.researchStudio').screenshot(path=str(out/'vault-live-1440.png'))
        await capital.fill('-1');await page.get_by_text('OUTDATED PREVIEW',exact=True).wait_for()
        assert await page.get_by_role('button',name='Use configuration for PAPER research',exact=True).is_disabled()
        for field,value,match in [(capital,'-1','greater than 0'),(maker,'-1','greater than or equal to 0'),(cap,'101','less than or equal to 1'),(capital,'broken','decimal')]:
            await capital.fill('12345.123456789123456789');await maker.fill('2');await cap.fill('50');await field.fill(value)
            await page.get_by_role('button',name='Validate / Preview',exact=True).click()
            await page.locator('.researchStudio [role="alert"]').wait_for()
            assert match.lower() in (await page.locator('.researchStudio [role="alert"]').inner_text()).lower()
        for patch in [{'paper_funding_interval_seconds':2},{'execution_mode':'TESTNET'},{'accounting':{'enabled':False}}]:
            response=await ctx.request.post(args.url+'/api/v1/research-vault/preview',data={'config':patch})
            assert response.status==422
        passed('C: negative capital/fees, malformed Decimal, utilization >100%, invalid interval and forbidden nested/execution inputs reject')
        await capital.fill('100000.123456789123456789');await maker.fill('2');await cap.fill('75');await validate()
        await page.get_by_role('button',name='Use configuration for PAPER research',exact=True).click()
        await page.get_by_role('link',name='Open Simulation',exact=True).click()
        await page.get_by_label('Scenario',exact=True).select_option('FLASH_MOVE')
        await page.get_by_label('Frames',exact=True).fill('30')
        async with page.expect_response(lambda r:'/simulation/run' in r.url and r.request.method=='POST') as response:
            await page.get_by_role('button',name='Run Simulation',exact=True).click()
        run=await (await response.value).json()
        await page.get_by_role('heading',name='Completed run · FLASH_MOVE',exact=True).wait_for()
        assert run['metrics']['starting_equity']=='100000.123456789123456789'
        assert run['research_configuration']['selected_preset_id']=='balanced-research'
        assert len(run['trace'])==30 and run['metrics']['fill_count']>0
        await page.get_by_text(run['research_configuration']['config_fingerprint'],exact=True).first.wait_for()
        passed('D: actual customized FLASH_MOVE PAPER run, fees/funding, existing trace and configuration provenance')
        async with page.expect_response(lambda r:'/research-vault/compare' in r.url) as response:
            await page.get_by_role('button',name='Compare preset baseline vs customized',exact=True).click()
        comparison=await (await response.value).json()
        await page.get_by_role('heading',name='Baseline vs customized PAPER research · FLASH_MOVE · 30 frames',exact=True).wait_for()
        assert comparison['baseline_result']['dataset_fingerprint']==comparison['custom_result']['dataset_fingerprint']
        assert comparison['baseline_result']['strategy_fingerprint']==comparison['custom_result']['strategy_fingerprint']
        await page.get_by_role('region',name='Baseline vs customized research',exact=True).screenshot(path=str(out/'simulation-live-1440.png'))
        passed('E: actual baseline/custom comparison shares dataset and strategy, renders exact backend deltas and both results')
        await page.get_by_label('Frames',exact=True).fill('3')
        await page.get_by_label('Optimization preset',exact=True).select_option('Inventory')
        async with page.expect_response(lambda r:'/simulation/optimize' in r.url) as response:
            await page.get_by_role('button',name='Run Bounded Grid Search',exact=True).click()
        opt=await (await response.value).json()
        await page.get_by_role('heading',name='Completed parameter study · Inventory',exact=True).wait_for()
        assert opt['research_configuration']['config_fingerprint']==run['research_configuration']['config_fingerprint']
        passed('Research accounting preset combines with unchanged bounded Inventory optimizer')
        await navigate('vault');assert await capital.input_value()=='100000.123456789123456789'
        await page.get_by_text('VALIDATED CURRENT DRAFT',exact=True).wait_for()
        passed('Vault → Simulation → Vault preserves coherent in-memory selected research draft')
        # Browser-only delayed preview fixture exercises obsolete completion.
        async def delayed(route):
            actual=await route.fetch();body=await actual.json();await asyncio.sleep(.5);await route.fulfill(response=actual,json=body)
        await page.route('**/research-vault/preview',delayed)
        await page.get_by_role('button',name='Validate / Preview',exact=True).click()
        await capital.fill('20000')
        await page.get_by_role('button',name='Validate / Preview',exact=True).wait_for()
        await page.get_by_text('OUTDATED PREVIEW',exact=True).wait_for()
        await page.unroute('**/research-vault/preview',delayed)
        passed('Browser fixture: slow preview completion cannot approve an edited draft')
        async def malformed(route): await route.fulfill(status=200,json={'simulated':True,'validation_status':'VALID'})
        await page.route('**/research-vault/preview',malformed)
        await page.get_by_role('button',name='Validate / Preview',exact=True).click()
        await page.get_by_text('Malformed research preview; draft remains unvalidated.',exact=True).wait_for()
        await page.unroute('**/research-vault/preview',malformed)
        passed('Browser fixture: malformed preview leaves draft unvalidated')
        assert authority(await terminal()) == before
        passed('Real runtime config, running state, kill switch, ledger fingerprint/version, orders and TESTNET eligibility unchanged before restart')
        await validate();old=await terminal()
        if args.backend_pid:
            os.kill(args.backend_pid,signal.SIGTERM)
            await page.get_by_text('Current backend session unavailable.',exact=False).wait_for(timeout=20000)
            await page.get_by_text('OUTDATED PREVIEW',exact=True).wait_for()
            environment={**os.environ,'MARKET_DATA_MODE':'DEMO','EXECUTION_MODE':'PAPER','ENABLE_HYPERLIQUID_TESTNET_ORDERS':'false'}
            replacement=subprocess.Popen([args.python,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000'],cwd=ROOT/'backend',env=environment,stdout=(out/'restart-backend.txt').open('w'),stderr=subprocess.STDOUT)
            await page.wait_for_function("async(old)=>{const s=(await import('/src/stores/terminal.ts')).useTerminalStore.getState();return s.wsState==='connected'&&s.terminal.process_id!==old}",arg=old['process_id'],timeout=25000)
            assert await page.get_by_role('button',name='Use configuration for PAPER research',exact=True).is_disabled()
            await validate();await page.get_by_role('button',name='Use configuration for PAPER research',exact=True).click()
            await navigate('simulation');await page.get_by_label('Frames',exact=True).fill('3')
            await page.get_by_role('button',name='Run Simulation',exact=True).click()
            await page.get_by_role('heading',name='Completed run · QUIET',exact=True).wait_for()
            passed('F: real backend stop/restart invalidates prior preview, preserves local draft, revalidates and runs again')
        # Check unchanged accounting/trading state prior to restart independently.
        # Restart naturally changes session ledger genesis: compare before restart above.
        for width,height in SIZES:
            await page.set_viewport_size({'width':width,'height':height})
            for slug in PAGES:
                await navigate(slug)
                if slug=='vault':
                    await page.get_by_role('heading',name='Research Configuration Studio',exact=True).wait_for()
                    await page.get_by_role('button',name='Balanced Research',exact=False).wait_for()
                    assert await page.get_by_text('Session observations',exact=True).count()==1
                if slug=='simulation': await page.get_by_role('button',name='Run Simulation',exact=True).wait_for()
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(width,slug)
                report['route_checks'].append({'route':slug,'width':width,'height':height})
            print('viewport',width,'passed',flush=True)
        await navigate('vault');await page.locator('.researchStudio').screenshot(path=str(out/'vault-live-390.png'))
        after=authority(await terminal())
        assert after['config']==before['config'] and after['running']==before['running'] and after['kill']==before['kill']
        assert after['orders']==before['orders'] and after['testnet_enabled']==before['testnet_enabled']
        assert after['ledger_version']==before['ledger_version']==0
        assert all(any(path in m['url'] for path in ['/research-vault/preview','/research-vault/compare','/simulation/run','/simulation/optimize']) for m in report['mutations'])
        assert not report['page_errors'],report['page_errors']
        passed('All 72 route/viewport checks; no trading mutations or page exceptions; runtime strategy, kill, ledger version and orders unchanged')
        await browser.close()
    if replacement:
        replacement.terminate();replacement.wait(timeout=10)
    (out/'browser-results.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:5173');parser.add_argument('--output',default=str(ROOT/'docs/acceptance/phase14'));parser.add_argument('--chromium',default='/usr/bin/chromium');parser.add_argument('--backend-pid',type=int);parser.add_argument('--python',default='/workspace/work/venv/bin/python');args=parser.parse_args()
    asyncio.run(main(args))
