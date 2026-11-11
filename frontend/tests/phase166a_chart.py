"""Chromium probes of the actual HistoryChart, React and lookup utility.

Used by the established native browser harness; no application test hooks.
The isolated page imports the same Vite modules and uses real canvas/mouse events.
"""
import asyncio
import re
from pathlib import Path


async def chart_acceptance(ctx, report, output=None):
    page = await ctx.new_page()
    await page.route('**/__phase166a_chart', lambda route: route.fulfill(
        content_type='text/html', body='<html><head></head><body><div id="chart" style="width:900px"></div></body></html>'))
    await page.goto('http://127.0.0.1:5173/__phase166a_chart')
    errors, console_errors = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: console_errors.append(message.text) if message.type == 'error' else None)
    # Use the actual production CSS without starting Vite's HMR websocket from
    # this fulfilled-document origin (Chromium applies a separate LAN check).
    frontend = Path(__file__).resolve().parents[1]
    styles = sorted((frontend / 'dist/assets').glob('*.css')) or [frontend / 'src/styles.css']
    for stylesheet in styles:
        await page.add_style_tag(content=stylesheet.read_text())
    await page.evaluate('''async()=>{
        const reactModule=await import('/node_modules/.vite/deps/react.js');
        const React=reactModule.default??reactModule;
        const clientModule=await import('/node_modules/.vite/deps/react-dom_client.js');
        const {createRoot}=clientModule.default??clientModule;
        const {HistoryChart,chartValue}=await import('/src/components/HistoryChart.tsx');
        const history=await import('/src/utils/terminalHistory.ts');
        const root=createRoot(document.getElementById('chart'));
        const points=Array.from({length:12},(_,i)=>({sequence:i+1,
            timestamp:`2026-11-11T10:11:${String(12+Math.floor(i/3)).padStart(2,'0')}.${String(i+1).padStart(6,'0')}Z`,
            equity:i===3?null:String(1000+i),session_pnl:i===3?null:String(i===0?0:i%2?-i:i)}));
        const line={key:'equity',label:'Equity',color:'#4cd4a1',unit:'quote'};
        const state={points,lines:[line],axis:'frame',fitKey:'same-run',commits:[],mounted:0,disconnected:0};
        const NativeResizeObserver=window.ResizeObserver;
        window.ResizeObserver=class extends NativeResizeObserver{
            constructor(...args){super(...args);state.mounted++}
            disconnect(){state.disconnected++;super.disconnect()}
        };
        const render=changes=>{
            Object.assign(state,changes);
            root.render(React.createElement(React.Profiler,{id:'HistoryChart',onRender:(id,phase,actualDuration,baseDuration)=>
                state.commits.push({phase,actual_ms:actualDuration,base_ms:baseDuration,
                    second_equity:state.points[1]?.equity,line_label:state.lines[0]?.label,
                    readout:document.querySelector('.chartReadout')?.textContent??''})},
                React.createElement(HistoryChart,{points:state.points,lines:state.lines,axis:state.axis,fitKey:state.fitKey})));
        };
        window.__chartProbe={state,render,root,chartValue,history,React,HistoryChart};
        render({});
    }''')
    chart = page.locator('.historyChart')
    readout = page.locator('.chartReadout')
    await chart.locator('canvas').first.wait_for()
    async def hover(frame):
        bounds = await chart.bounding_box()
        for i in range(1, 101):
            await page.mouse.move(bounds['x'] + i * (bounds['width'] - 85) / 100,
                bounds['y'] + 60)
            text = await readout.inner_text()
            match = re.search(r'Frame (\d+) ', text)
            if match and int(match.group(1)) == frame:
                return text
        raise AssertionError(f'Cannot hover actual frame {frame}: {await readout.inner_text()}')
    text = await hover(2)
    assert 'Equity: 1001 quote' in text, text
    assert '10:11:12.000002' in text, text
    # Check every actual React commit, before passive chart effects can emit a
    # replacement crosshair event and conceal a stale formatted readout.
    await page.evaluate('''()=>{const p=window.__chartProbe;p.render({points:p.state.points.map(x=>({...x,equity:x.equity===null?null:String(Number(x.equity)+100)}))})}''')
    await page.wait_for_timeout(80)
    commits = await page.evaluate('()=>window.__chartProbe.state.commits.filter(c=>c.second_equity==="1101")')
    stale = [c for c in commits if re.search(r'Equity:\s*1001 quote', c['readout'])]
    report['chart_point_revision_commits'] = commits
    report['chart_point_revision_no_stale_commit'] = not stale
    assert not stale, f'Replaced source points commit the previous formatted hover: {stale}'
    assert 'Equity: 1101 quote' in await hover(2)
    await page.evaluate('''()=>{const p=window.__chartProbe;p.render({lines:[{key:'session_pnl',label:'PnL',color:'#fff',signed:true,unit:'quote'}]})}''')
    await page.wait_for_timeout(80)
    commits = await page.evaluate('()=>window.__chartProbe.state.commits.filter(c=>c.line_label==="PnL")')
    assert not any('Equity:' in c['readout'] for c in commits), commits
    assert 'PnL: 0 quote' in await hover(1)
    assert 'PnL: -1 quote' in await hover(2)
    assert 'PnL: 2 quote' in await hover(3)
    assert 'Unavailable' in await hover(4)
    await page.get_by_role('button', name='Reset PnL chart view', exact=True).click()
    await page.evaluate("()=>window.__chartProbe.render({axis:'time',fitKey:'live-session'})")
    await page.wait_for_timeout(80)
    assert 'over backend observation time' in await chart.get_attribute('aria-label')
    # New receipt in the same session, then independent segment with reused
    # sequences. Neither update may inherit prior values or tooltip state.
    await page.evaluate('''()=>{const p=window.__chartProbe;p.render({points:[...p.state.points,{sequence:13,timestamp:'2026-11-11T10:11:16.000013Z',session_pnl:'99'}]})}''')
    await page.wait_for_timeout(80)
    assert 'Equity:' not in await readout.inner_text()
    await page.evaluate('''()=>{const p=window.__chartProbe;p.render({axis:'frame',fitKey:'independent-segment',
        points:p.state.points.slice(0,6).map(x=>({...x,session_pnl:'777'}))})}''')
    await page.wait_for_timeout(80)
    assert 'PnL: 777 quote' in await hover(2)
    if output is not None:
        await page.screenshot(path=str(output / 'history-chart-hover.png'), full_page=True)
        report['screenshots'].append('history-chart-hover.png')
    await page.mouse.move(1100, 800)
    await page.evaluate('''()=>{const p=window.__chartProbe;
        p.root.render(null)}''')
    await page.wait_for_timeout(80)
    assert await page.locator('canvas').count() == 0
    await page.evaluate('()=>window.__chartProbe.render({fitKey:"remounted-run"})')
    await chart.locator('canvas').first.wait_for()
    assert 'Hover a point' in await readout.inner_text()
    assert 'PnL: 777 quote' in await hover(2)
    report['chart_component'] = await page.evaluate('''()=>{
        const p=window.__chartProbe,s=p.state;
        return {commits:s.commits,resize_observers_created:s.mounted,resize_observers_disconnected:s.disconnected,
            canvas_count:document.querySelectorAll('canvas').length};
    }''')
    # Actual browser utility benchmark, alternating order; no financial math.
    report['crosshair_lookup'] = await page.evaluate('''()=>{
        const h=window.__chartProbe.history;
        const points=Array.from({length:250},(_,i)=>({sequence:i+1,timestamp:new Date(1762855200000+i*1000).toISOString(),equity:String(i)}));
        const batches=30,lookups=1000,indexedLookups=100000,results={};
        for(const axis of ['frame','time']){
            const index=h.chartObservationIndex(points,axis),old=[],indexed=[],build=[];
            const keys=points.map(p=>axis==='frame'?p.sequence:Math.floor(Date.parse(p.timestamp)/1000));
            const legacy=key=>[...(axis==='frame'?points:h.boundedObservations(points,1000))].reverse().find(p=>
                axis==='frame'?p.sequence===key:Math.floor(Date.parse(p.timestamp)/1000)===key);
            for(const key of keys)if(legacy(key)!==index.get(key))throw Error('lookup mismatch');
            for(let i=0;i<batches;i++){
                let start=performance.now();h.chartObservationIndex(points,axis);build.push(performance.now()-start);
                for(const kind of i%2?['legacy','indexed']:['indexed','legacy']){
                    start=performance.now();let checksum=0;
                    const count=kind==='legacy'?lookups:indexedLookups;
                    for(let j=0;j<count;j++){
                        const point=kind==='legacy'?legacy(keys[j%keys.length]):index.get(keys[j%keys.length]);
                        checksum+=point.sequence;
                    }
                    window.__lookupSink=checksum;
                    (kind==='legacy'?old:indexed).push(performance.now()-start);
                }
            }
            results[axis]={points:points.length,batches,legacy_lookups_per_batch:lookups,
                indexed_lookups_per_batch:indexedLookups,legacy_batch_ms:old,indexed_batch_ms:indexed,index_build_ms:build,
                note:'Normalize by each batch count; larger indexed batches avoid timer-resolution zeros. Source index construction is separate.'};
        }
        return results;
    }''')
    report['chart_component']['after_hover'] = await page.evaluate('''async()=>{
        const gaps=[];let previous=performance.now();for(let i=0;i<30;i++){
            await new Promise(requestAnimationFrame);let now=performance.now();gaps.push(now-previous);previous=now}
        return {animation_frame_ms:gaps,heap_used_bytes:performance.memory?.usedJSHeapSize??null,
            note:'Observed Chromium process heap/frame intervals; not independent allocations or latency guarantees'};
    }''')
    await page.evaluate('()=>window.__chartProbe.root.unmount()')
    await page.wait_for_timeout(80)
    final = await page.evaluate('''()=>({created:window.__chartProbe.state.mounted,
        disconnected:window.__chartProbe.state.disconnected,canvases:document.querySelectorAll('canvas').length})''')
    assert final['canvases'] == 0 and final['created'] == final['disconnected'], final
    assert not errors, errors
    assert not console_errors, console_errors
    report['chart_component']['unmount'] = final
    report['chart_component']['page_errors'] = errors
    report['chart_component']['console_errors'] = console_errors
    await page.close()
