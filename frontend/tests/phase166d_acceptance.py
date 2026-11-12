"""Missing final diagnostic regressions in the existing Chromium harness."""
import asyncio


async def final_diagnostics_acceptance(page, control, status, passed):
    await page.set_viewport_size({'width': 1440, 'height': 900})
    # Earlier connection-transition probes correctly retire Vault approval.
    # Validate explicitly for this independent comparison, never revive it.
    await page.evaluate("location.hash='#/vault'")
    await page.get_by_role('heading', name='Research vault & accounting', exact=True).wait_for()
    await page.get_by_role('button', name='Validate / Preview', exact=True).click()
    choose = page.get_by_role('button', name='Use configuration for PAPER research', exact=True)
    async with asyncio.timeout(20):
        while not await choose.is_enabled():
            await asyncio.sleep(.05)
    await choose.click()
    await page.evaluate("location.hash='#/simulation'")
    await page.get_by_role('button', name='Scenario & optimization', exact=True).click()
    await page.get_by_label('Frames', exact=True).fill('3')
    before = (await status())['authority']
    # Consume error clones promptly. DevTools response.text() can wait forever
    # when the actual client intentionally ignores an untrusted error body.
    await page.evaluate('''()=>{
        window.__finalDiagnosticBodies=[];
        const original=window.fetch;
        window.__beforeFinalDiagnosticsFetch=original;
        window.fetch=async(...args)=>{
            const reply=await original(...args);
            if(!reply.ok&&['/simulation/run','/research-vault/compare'].some(p=>String(args[0]).endsWith(p)))
                reply.clone().text().then(text=>window.__finalDiagnosticBodies.push(text));
            return reply;
        };
    }''')
    for button, path in [
        ('Run Simulation', '/api/v1/simulation/run'),
        ('Compare preset baseline vs customized', '/api/v1/research-vault/compare'),
    ]:
        submit = page.get_by_role('button', name=button, exact=True)
        async with asyncio.timeout(20):
            while not await submit.is_enabled():
                await asyncio.sleep(.05)
        for failure, code in [('value', 422), (True, 500)]:
            await control(failure=failure)
            count = await page.evaluate('window.__finalDiagnosticBodies.length')
            async with page.expect_response(lambda r: r.url.endswith(path)) as wait:
                await submit.click()
            reply = await wait.value
            assert reply.status == code
            await page.wait_for_function('(count)=>window.__finalDiagnosticBodies.length>count', arg=count)
            wire = await page.evaluate('window.__finalDiagnosticBodies.at(-1)')
            alert = page.get_by_role('alert').filter(has_text=f'HTTP {code}')
            await alert.wait_for()
            visible = await alert.inner_text()
            for text in (wire, visible):
                assert all(secret not in text for secret in
                    ('/private/', 'API_KEY', 'fixture-secret', 'Traceback')), text
            assert (await status())['authority'] == before
        await control(failure=False)
    passed('16.6D real Scenario/Vault HTTP 422 and sanitized 500 from injected engine errors; private diagnostics hidden and operational authority unchanged')
    # A proxy's untrusted error body must also be safe in the actual Scenario UI.
    await page.route('**/simulation/run', lambda route: route.fulfill(status=500,
        content_type='application/json', body='{"detail":"Traceback /private/proxy API_KEY=synthetic-secret"}'))
    try:
        await page.get_by_role('button', name='Run Simulation', exact=True).click()
        alert = page.get_by_role('alert').filter(has_text='HTTP 500')
        await alert.wait_for()
        visible = await alert.inner_text()
        assert all(s not in visible for s in
            ('Traceback', '/private/', 'API_KEY', 'synthetic-secret'))
    finally:
        await page.unroute('**/simulation/run')
    await page.get_by_role('button', name='Run Simulation', exact=True).click()
    await page.get_by_role('region', name='Completed simulation', exact=True).wait_for()
    assert (await status())['authority'] == before
    await page.evaluate('window.fetch=window.__beforeFinalDiagnosticsFetch')
    passed('16.6D labeled untrusted proxy error stays private in actual Scenario UI; manual retry runs the real engine successfully')
