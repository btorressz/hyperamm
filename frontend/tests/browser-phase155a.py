"""Phase 15.4 genuine Chromium harness plus offline security/session/terminal acceptance.

No image mocks, venue calls, order writes or production fixture registrations.
"""
import argparse,asyncio,importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('browser154',Path(__file__).with_name('browser-phase154.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

async def additional(s):
    page,ctx,control,nav,workspace,store,capture,passed,report=[s[k] for k in ('page','ctx','control','nav','workspace','store','capture','passed','report')]
    out=Path(s['args'].output)
    async def screenshot(name):
        await page.evaluate('document.fonts.ready');await page.screenshot(path=str(out/name),full_page=True)
    async def artifact():return (await store())['artifact']
    async def live_state():return await page.evaluate("async()=>{const s=(await import('/src/stores/liveMarkets.ts')).useLiveMarketStore.getState();return {current:s.current,status:s.streamStatus}}")
    # Real origin-aware HTTP/WS boundary. Requests carry synthetic hostile headers;
    # the actual local application remains running and its strategy stays stopped.
    for origin in ['http://localhost:9999','http://evil.example','null','ftp://localhost']:
        r=await ctx.request.post('http://127.0.0.1:8000/api/v1/strategy/start',headers={'Origin':origin})
        assert r.status==403,(origin,r.status)
    r=await ctx.request.get('http://127.0.0.1:8000/api/v1/health',headers={'Origin':'http://127.0.0.1:5173'})
    assert r.status==200
    rejected=await page.evaluate("""async()=>{const iframe=document.createElement('iframe');iframe.src='about:blank';document.body.appendChild(iframe);iframe.remove();return fetch('/api/v1/health',{headers:{'X-Forwarded-For':'127.0.0.1'}}).then(r=>r.status)}""")
    assert rejected==403
    passed('Real HTTP boundary rejects unrelated localhost/remote/null/non-HTTP origins and forwarding headers; configured Vite access succeeds')
    await control(kind='active');rid=await s['run']('BTC');await workspace();await s['select']('BTC',rid)
    a=await capture(refresh=True);assert not a['historicalReason']
    await page.set_viewport_size({'width':1440,'height':900});await screenshot('market-comparison-1440.png')
    await page.set_viewport_size({'width':390,'height':844});await screenshot('market-comparison-390.png')
    await page.set_viewport_size({'width':1440,'height':900})
    await control(kind='stale',action='publish');a=await capture(refresh=True)
    text=await page.locator('.marketResearchWorkspace').inner_text();assert 'STALE · Observed native L2 exchange time' in text
    assert a['data']['metrics'][0]['observed_value'] is not None and a['data']['metrics'][0]['absolute_difference'] is None
    await screenshot('stale-evidence-1440.png')
    passed('Retained stale midpoint is visible with STALE label and original source time; no stale numerical price delta')
    await control(kind='active',action='publish');await capture(refresh=True)
    frozen=(await artifact())['data']
    await ctx.set_offline(True)
    await page.wait_for_function("async()=>!(await import('/src/stores/liveMarkets.ts')).useLiveMarketStore.getState().current")
    await page.wait_for_function("async()=>!!(await import('/src/stores/marketResearchComparison.ts')).useMarketResearchComparisonStore.getState().artifact.historicalReason")
    assert (await artifact())['data']==frozen
    assert 'HISTORICAL · Observed native L2 exchange time' in await page.locator('.marketResearchWorkspace').inner_text()
    await ctx.set_offline(False);await page.wait_for_timeout(800)
    assert (await artifact())['historicalReason']
    passed('Real browser offline/online preserves exact artifact as HISTORICAL; reconnect never silently reactivates it')
    # Real delayed response after unmount: HTTP completion cannot restore a capture.
    ready,release=asyncio.Event(),asyncio.Event()
    async def delay(route):
        response=await route.fetch();ready.set();await release.wait()
        try:await route.fulfill(response=response)
        except Exception:pass
    await page.route('**/research-market-comparison/compare',delay)
    await page.get_by_role('button',name='Refresh observed comparison',exact=True).click();await asyncio.wait_for(ready.wait(),10)
    await nav('vault');release.set();await page.wait_for_timeout(250);await page.unroute('**/research-market-comparison/compare',delay)
    await workspace();assert (await artifact())['data']==frozen and (await artifact())['historicalReason']
    passed('Component unmount during an actual pending POST rejects its delayed completion')
    # HTTP failures/loading/invalid completed evidence do not mutate the selection.
    await page.route('**/research-market-comparison/compare',lambda r:r.fulfill(status=503,json={'detail':'Deterministic unavailable fixture'}))
    await page.get_by_role('button',name='Refresh observed comparison',exact=True).click()
    await page.locator('.marketResearchWorkspace [role=alert]').wait_for()
    assert (await artifact())['data']==frozen
    await page.unroute('**/research-market-comparison/compare')
    invalid=await page.evaluate("async()=>{const s=(await import('/src/stores/marketResearchComparison.ts')).useMarketResearchComparisonStore;const before=s.getState();try{s.getState().retain({simulated:false});return false}catch{return s.getState()===before}}")
    assert invalid
    passed('503 comparison error is visible; invalid completed research cannot replace valid retained evidence')
    # Every requested terminal route, navigation and layout at the six required sizes.
    routes=['dashboard','markets','simulation','vault','agents','risk','execution','settings','logs']
    report['terminal_viewports']=[]
    for w,h in base.SIZES:
        await page.set_viewport_size({'width':w,'height':h})
        for slug in routes:
            await nav(slug)
            title=page.get_by_text('Risk Management',exact=True) if slug=='risk' else page.locator('main h1').first
            await title.wait_for()
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(slug,w)
            assert await title.is_visible()
            report['terminal_viewports'].append({'route':slug,'width':w,'height':h,'result':'PASS'})
            if slug=='simulation' and w==1440:await screenshot('simulation-1440.png')
            if slug=='markets':
                for label in ['Operational Market','Live Market Intelligence','Market vs Research']:
                    await page.get_by_role('button',name=label,exact=True).click();await page.wait_for_timeout(120)
                    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(label,w)
                    if label=='Live Market Intelligence' and w==1440:await screenshot('live-markets-1440.png')
        passed(f'All terminal routes plus three Markets views at {w}px: visible headings/navigation and zero document overflow')
    # Exercise actual desktop links and the mobile drawer as well as route loading.
    for width in [1440,390]:
        await page.set_viewport_size({'width':width,'height':900})
        if width==390:await page.get_by_role('button',name='Open navigation',exact=True).click()
        await page.get_by_role('link',name='Dashboard',exact=True).click()
        await page.get_by_role('heading',name='Liquidity terminal',exact=True).wait_for()
        if width==390:assert not await page.get_by_role('button',name='Close navigation',exact=True).is_visible()
    passed('Desktop navigation links and mobile drawer navigate to Dashboard and close correctly')
    await page.set_viewport_size({'width':1440,'height':900});await nav('markets')
    await page.get_by_role('button',name='Live Market Intelligence',exact=True).click()
    await control(kind='unavailable',action='close');await nav('vault');await nav('markets');await page.get_by_role('button',name='Live Market Intelligence',exact=True).click()
    await page.wait_for_function("async()=>(await import('/src/stores/liveMarkets.ts')).useLiveMarketStore.getState().streamStatus==='UNAVAILABLE'")
    assert 'UNAVAILABLE' in await page.locator('main').inner_text(),await page.locator('main').inner_text()
    await control(kind='disabled');await nav('vault');await nav('markets');await page.get_by_role('button',name='Live Market Intelligence',exact=True).click()
    await page.wait_for_function("async()=>(await import('/src/stores/liveMarkets.ts')).useLiveMarketStore.getState().streamStatus==='DISABLED'")
    assert 'DISABLED' in await page.locator('main').inner_text(),await page.locator('main').inner_text()
    passed('Unavailable provider and disabled live states render safely after navigation')
    assert not report['page_errors'],report['page_errors']
    assert all('/simulation/run' in r['url'] or '/research-market-comparison/compare' in r['url'] for r in report['mutations'])
    assert sum('/simulation/run' in r['url'] for r in report['mutations'])==4
    report['screenshots']=sorted(p.name for p in out.glob('*.png'))
    report['classification']='PASS'

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--python',default='python');parser.add_argument('--chromium',default='/usr/bin/chromium');parser.add_argument('--url',default='http://127.0.0.1:5173');parser.add_argument('--output',default=str(ROOT/'docs/acceptance/phase155a'))
    args=parser.parse_args();args.work_name='browser155a';args.extra_acceptance=additional
    asyncio.run(base.main(args))
