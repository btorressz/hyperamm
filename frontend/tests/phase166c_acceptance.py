"""Phase 16.6C cases within the existing real Chromium/FastAPI harness."""
import asyncio

async def research_acceptance(page, ctx, control, status, idle, restart, out, report, passed):
    replay_posts=[]
    page.on('request',lambda r:replay_posts.append(r.url) if r.method=='POST' and r.url.endswith('/historical-replay/run') else None)
    replay=page.get_by_role('region',name='Historical Replay Studio',exact=True)
    state=replay.get_by_role('status',name='Historical replay research state',exact=True)
    button=replay.get_by_role('button',name='Run Historical PAPER Replay',exact=True)
    async def enabled():
        async with asyncio.timeout(30):
            while not await button.is_enabled():await asyncio.sleep(.05)
    async def select(name='BTC-complete-fixture'):
        await replay.get_by_role('combobox',name='Historical dataset',exact=True).select_option(name)
        await enabled()
    async def shot(name, locator=None):
        await page.evaluate('window.scrollTo(0,0)')
        if locator:
            await locator.screenshot(path=str(out/name),style='.topbar,.sidebar,.skipLink{visibility:hidden!important}')
        else:
            await replay.screenshot(path=str(out/name),style='.topbar,.sidebar,.skipLink{visibility:hidden!important}')
        report['screenshots'].append(name)
    async def run(code=200):
        await enabled()
        async with page.expect_response(lambda r:r.url.endswith('/historical-replay/run')) as wait:
            await button.click()
        response=await wait.value
        assert response.status==code,await response.text()
        if code==200:
            await replay.get_by_role('heading',name='Replay receipt',exact=True).wait_for()
            assert 'COMPLETE' in await state.inner_text()
        else:await replay.get_by_role('alert',name='Research diagnostics',exact=True).wait_for()
        return response.status
    assert await state.count()==0
    assert not await button.is_enabled()
    await replay.get_by_text('No dataset selected.',exact=False).wait_for()
    await control(storage='empty')
    await replay.get_by_role('button',name='Refresh catalog',exact=True).click()
    await replay.get_by_text('0 admitted datasets available.',exact=False).wait_for()
    assert await replay.get_by_role('combobox',name='Historical dataset',exact=True).locator('option').count()==1
    await control(storage='vault')
    await replay.get_by_role('button',name='Refresh catalog',exact=True).click()
    await select('phase165d-1000-1-0-0')
    preview=replay.get_by_role('region',name='Research workload preview',exact=True)
    assert 'BTC-PERP' in await preview.inner_text() and 'Synthetic fixture' in await preview.inner_text()
    assert '1001' in await preview.inner_text()
    for n in ['2','128','999','1000','4999','5000','1','5001']:
        await replay.get_by_role('spinbutton',name='Maximum frames',exact=True).fill(n)
        assert ('Invalid frame limit' in await preview.inner_text())==(n in ['1','5001'])
        assert await replay.locator('.researchWorkloadWarning').filter(has_text='Large research request').count()==int(1000<=int(n)<=5000)
    await replay.get_by_role('spinbutton',name='Maximum frames',exact=True).fill('5000')
    contrast=await preview.locator('dt,dd').evaluate_all(r'''nodes=>{
        const rgb=s=>s.match(/[\d.]+/g).slice(0,3).map(Number);
        const luminance=c=>c.map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4}).reduce((a,x,i)=>a+x*[.2126,.7152,.0722][i],0);
        return Math.min(...nodes.map(n=>{
            let p=n;while(p&&getComputedStyle(p).backgroundColor==='rgba(0, 0, 0, 0)')p=p.parentElement;
            const a=luminance(rgb(getComputedStyle(n).color)),b=luminance(rgb(getComputedStyle(p).backgroundColor));
            return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
        }));
    }''')
    assert contrast>=4.5,contrast
    report['workload_min_text_contrast']=round(contrast,2)
    await shot('large-workload-warning.png',preview)
    for w,h in [(1920,1080),(1440,900),(1024,768),(768,900),(390,844)]:
        await page.set_viewport_size({'width':w,'height':h})
        await asyncio.sleep(.1)
        assert await page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1')
        if w==390:await shot('mobile-preflight-390.png',preview)
        if w==1440:await shot('historical-preflight-1440.png')
    await page.set_viewport_size({'width':390,'height':844})
    await select('BTC-'+('long-admitted-identifier-'*5)[:116])
    assert await page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1')
    await select()
    assert 'User-asserted recording' in await preview.inner_text()
    await page.set_viewport_size({'width':1440,'height':900})
    for market in ['ETH','SOL']:
        await select(market+'-complete-fixture')
        assert market+'-PERP' in await preview.inner_text()
        assert 'Synthetic fixture' in await preview.inner_text()
    await select('BTC-gap-fixture')
    await replay.get_by_role('spinbutton',name='Maximum frames',exact=True).fill('4')
    await control(delay=.35)
    before_posts=len(replay_posts)
    async with page.expect_request(lambda r:r.url.endswith('/historical-replay/run')):
        # Same-task clicks must create only one computational request.
        await button.evaluate('(b)=>{b.click();b.click();b.click()}')
    await state.filter(has_text='AWAITING BACKEND').wait_for()
    assert 'worker running' not in await replay.inner_text()
    await replay.get_by_role('heading',name='Replay receipt',exact=True).wait_for()
    assert 'COMPLETE' in await state.inner_text()
    assert len(replay_posts)==before_posts+1
    await control(delay=0)
    await replay.get_by_role('combobox',name='Replay segment',exact=True).select_option('1')
    await replay.get_by_role('button',name='Next',exact=True).click()
    assert await replay.locator('canvas').count()>0
    await shot('research-complete.png')
    await replay.get_by_role('combobox',name='Execution model',exact=True).select_option('MODELED_CROSSING')
    await state.filter(has_text='RETIRED').wait_for()
    assert not await replay.get_by_role('heading',name='Replay receipt',exact=True).count()
    await run()
    # A same-session connection round trip cannot restore previous metrics.
    for ws in ['disconnected','connected']:
        await page.evaluate("async(s)=>{const m=await import('/src/stores/terminal.ts');m.useTerminalStore.getState().setWsState(s)}",ws)
        await state.filter(has_text='RETIRED').wait_for()
        assert not await replay.locator('canvas').count()
    await select();await control(delay=.5)
    async with page.expect_request(lambda r:r.url.endswith('/historical-replay/run')):
        await button.click()
    await replay.get_by_role('combobox',name='Historical dataset',exact=True).select_option('ETH-complete-fixture')
    await idle();await asyncio.sleep(.2)
    await state.filter(has_text='RETIRED').wait_for()
    assert not await replay.locator('canvas').count()
    await control(delay=0)
    passed('16.6C historical idle/empty catalog, actual BTC/ETH/SOL source preview, all frame boundaries, five widths, running/complete, segment/frame/chart navigation, modeled rerun, input and same-session retirement')
    await select('BTC-missing-fixture');await run(422)
    assert 'VALIDATION' in await replay.get_by_role('alert',name='Research diagnostics').inner_text()
    await select();await control(storage='disabled');await run(503)
    await page.set_viewport_size({'width':390,'height':844})
    await shot('research-diagnostic-390.png',replay.get_by_role('alert',name='Research diagnostics'))
    await page.set_viewport_size({'width':1440,'height':900})
    await control(storage='vault',delay=.5)
    # Hold the existing single slot with actual engine work.
    request=(await (await ctx.request.get('http://127.0.0.1:8000/api/v1/historical-replay/dataset-summaries')).json())[0]
    body={'dataset_id':request['dataset_id'],'dataset_fingerprint':request['dataset_fingerprint'],'market':request['market'],'execution':{'size_decimals':5},'max_frames':4}
    held=asyncio.create_task(ctx.request.post('http://127.0.0.1:8000/api/v1/historical-replay/run',data=body))
    async with asyncio.timeout(10):
        while not (await status())['busy']:await asyncio.sleep(.02)
    await run(429);assert 'BUSY' in await replay.get_by_role('alert',name='Research diagnostics').inner_text()
    assert (await held).status==200
    await idle();await control(delay=0)
    # Request-size fault sent through the actual FastAPI body-limit middleware.
    await page.route('**/historical-replay/run',lambda route:route.continue_(post_data=' '*65537))
    await run(413)
    assert 'SIZE' in await replay.get_by_role('alert',name='Research diagnostics').inner_text()
    await page.unroute('**/historical-replay/run')
    # Test-only engine failure; the unchanged production route sanitizes HTTP 500.
    await control(failure=True)
    await run(500)
    text=await replay.get_by_role('alert',name='Research diagnostics').inner_text()
    assert 'SERVER' in text and 'fixture-secret' not in text and '/private' not in text and 'Traceback' not in text
    await control(failure=False)
    await run()
    await restart()
    await state.filter(has_text='RETIRED').wait_for(timeout=30000)
    assert not await replay.locator('canvas').count()
    await select();await run()
    # Refresh detaches the browser, but the same existing worker stays occupied.
    await control(delay=1)
    async with page.expect_request(lambda r:r.url.endswith('/historical-replay/run')):await button.click()
    async with asyncio.timeout(10):
        while not (await status())['busy']:await asyncio.sleep(.02)
    await page.reload()
    assert (await status())['busy']
    await idle();await control(delay=0)
    await page.get_by_role('button',name='Historical replay',exact=True).click()
    assert not await replay.get_by_role('heading',name='Replay receipt',exact=True).count()
    await select()
    # Actual process death during admission, followed by a fresh backend session.
    await control(delay=1)
    async with page.expect_request(lambda r:r.url.endswith('/historical-replay/run')):await button.click()
    async with asyncio.timeout(10):
        while not (await status())['busy']:await asyncio.sleep(.02)
    await restart(kill=True)
    await state.filter(has_text='RETIRED').wait_for(timeout=30000)
    assert not await replay.locator('canvas').count()
    await select();await control(delay=0);await run()
    passed('16.6C actual historical HTTP 422/429/503, actual body-limit 413 and test-injected engine failure with safe HTTP 500, refresh retains worker ownership, backend restart/death during admitted replay retires evidence and manual rerun recovers')
