"""Optional real-browser acceptance. Requires local DEMO/PAPER Uvicorn + Vite.
Run with system Python containing Playwright; never installs browser dependencies.
--paper-controls explicitly exercises existing config/simulation/start/kill/resume.
"""
import argparse
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

PAGES = ['dashboard', 'markets', 'strategy', 'amm-settings', 'execution', 'risk',
         'agents', 'vault', 'analytics', 'simulation', 'logs', 'settings']
SIZES = [(1920,1080), (1440,900), (1366,768), (1024,768), (768,900), (390,844)]

async def main(args):
 output = Path(args.output)
 output.mkdir(parents=True, exist_ok=True)
 report = {'layout_checks': [], 'page_errors': [], 'console_errors': [], 'workflows': []}
 async with async_playwright() as p:
  browser = await p.chromium.launch(executable_path=args.chromium, headless=True, args=['--no-sandbox'])
  context = await browser.new_context(timezone_id='America/Los_Angeles')
  page = await context.new_page()
  page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
  page.on('console', lambda message: report['console_errors'].append(message.text) if message.type == 'error' else None)
  async def route(slug):
   await page.goto(f'{args.url}/#/{slug}')
   await page.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED')
   await page.wait_for_function('document.querySelector("#page-content")?.innerText.length > 30')
  for width,height in SIZES:
   await page.set_viewport_size({'width':width,'height':height})
   for slug in PAGES:
    await route(slug)
    geometry = await page.evaluate('''() => {
      const kill = document.querySelector('.headerKill').getBoundingClientRect();
      return {width:innerWidth, scroll:document.documentElement.scrollWidth,
        kill:{x:kill.x,y:kill.y,right:kill.right,bottom:kill.bottom}};
    }''')
    assert geometry['scroll'] <= width+1, (width,slug,geometry)
    kill=geometry['kill']
    assert kill['x'] >= 0 and kill['right'] <= width and kill['y'] >= 0 and kill['bottom'] <= height, (slug,geometry)
    assert await page.locator('#page-content').get_attribute('aria-label')
    assert not await page.locator('#page-content').get_by_text('Terminal payload could not be rendered').count()
    report['layout_checks'].append({'page':slug,'width':width,'height':height,**geometry})
    if width==1440 and slug in ['dashboard','markets','risk','settings']:
     await page.screenshot(path=str(output/f'{slug}-1440.png'),full_page=True)
    if width==390 and slug=='dashboard':
     await page.screenshot(path=str(output/'dashboard-mobile.png'),full_page=True)
  await page.set_viewport_size({'width':1440,'height':900})
  await route('markets')
  await page.get_by_role('link',name='Risk',exact=True).click()
  await page.wait_for_url('**/#/risk')
  await page.reload()
  await page.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED')
  assert await page.get_by_role('link',name='Risk',exact=True).get_attribute('aria-current') == 'page'
  await page.get_by_role('link',name='Vault',exact=True).click()
  await page.wait_for_url('**/#/vault')
  await page.go_back(); await page.wait_for_url('**/#/risk')
  await page.go_forward(); await page.wait_for_url('**/#/vault')
  await page.get_by_role('button',name='Collapse navigation',exact=True).click()
  assert await page.get_by_role('button',name='Expand navigation',exact=True).get_attribute('aria-expanded')=='false'
  assert (await page.locator('.sidebar').bounding_box())['width'] == 68
  await page.reload(); await page.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED')
  assert (await page.locator('.sidebar').bounding_box())['width'] == 68
  await page.get_by_role('button',name='Expand navigation',exact=True).click()
  await route('settings')
  await page.get_by_label('Layout density').select_option('dense')
  assert await page.locator('.app').evaluate('(e)=>e.classList.contains("dense")')
  await page.reload(); await page.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED')
  assert await page.get_by_label('Layout density').input_value()=='dense'
  await page.get_by_label('Layout density').select_option('comfortable')
  report['workflows'].extend(['refresh/back/forward','collapse persistence','density persistence'])
  await page.goto(f'{args.url}/#/unknown')
  await page.wait_for_url('**/#/dashboard')
  await page.reload()
  await page.wait_for_selector('.headerBadges >> text=TERMINAL CONNECTED')
  await page.keyboard.press('Tab')
  assert await page.get_by_role('link',name='Skip to workspace').evaluate('(e)=>e===document.activeElement')
  await page.keyboard.press('Enter')
  assert await page.locator('#page-content').evaluate('(e)=>e===document.activeElement')
  assert page.url.endswith('#/dashboard')
  report['workflows'].extend(['invalid-route fallback','skip-link keyboard focus'])
  await page.set_viewport_size({'width':390,'height':844})
  await page.get_by_role('button',name='Open navigation',exact=True).click()
  assert await page.get_by_role('dialog',name='Terminal navigation').is_visible()
  assert await page.locator('main').get_attribute('inert') is not None
  await page.get_by_role('link',name='Settings',exact=True).focus()
  await page.keyboard.press('Tab')
  assert await page.get_by_role('button',name='Close navigation',exact=True).evaluate('(e)=>e===document.activeElement')
  await page.keyboard.press('Shift+Tab')
  assert await page.get_by_role('link',name='Settings',exact=True).evaluate('(e)=>e===document.activeElement')
  await page.keyboard.press('Escape')
  assert await page.get_by_role('button',name='Open navigation',exact=True).evaluate('(e)=>e===document.activeElement')
  await page.get_by_role('button',name='Open navigation',exact=True).click()
  await page.get_by_role('link',name='Markets',exact=True).click()
  await page.wait_for_url('**/#/markets')
  assert not await page.get_by_role('dialog').count()
  report['workflows'].extend(['mobile focus trap/Escape/return','mobile page navigation'])
  if args.paper_controls:
   await page.set_viewport_size({'width':1440,'height':900})
   async def terminal():
    return await page.evaluate("async () => (await import('/src/stores/terminal.ts')).useTerminalStore.getState().terminal")
   before=await terminal()
   assert before['market']['mode']=='DEMO' and before['strategy']['config']['execution_mode']=='PAPER'
   assert not before['diagnostics']['testnet_enabled'] and not before['strategy']['running'] and not before['risk']['kill_switch_active']
   await route('amm-settings')
   field=page.get_by_label('Virtual base reserve',exact=True)
   old=await field.input_value()
   await field.fill('0')
   assert (await terminal())['strategy']['config']==before['strategy']['config']
   await page.get_by_role('button',name='Save',exact=True).click()
   await page.wait_for_selector('.inlineError')
   assert (await terminal())['strategy']['config']==before['strategy']['config']
   await page.get_by_role('button',name='Reset',exact=True).click()
   assert await field.input_value()==old
   # Exercise a valid edit, then restore the exact original config while stopped.
   await field.fill(str(float(old)*2))
   await page.get_by_role('button',name='Save',exact=True).click()
   await page.wait_for_selector('text=Configuration saved.')
   await field.fill(old)
   await page.get_by_role('button',name='Save',exact=True).click()
   await page.wait_for_selector('text=Configuration saved.')
   await page.wait_for_function("async (config) => JSON.stringify((await import('/src/stores/terminal.ts')).useTerminalStore.getState().terminal.strategy.config) === JSON.stringify(config)",arg=before['strategy']['config'])
   await route('simulation')
   await page.get_by_label('Frames',exact=True).fill('20')
   async with page.expect_response(lambda r:'/simulation/run' in r.url and r.request.method=='POST') as response:
    await page.get_by_role('button',name='Run Simulation',exact=True).click()
   assert (await response.value).ok
   after=await terminal()
   assert after['strategy']['config']==before['strategy']['config'] and not after['strategy']['running']
   await route('dashboard')
   await page.get_by_role('button',name='Start',exact=True).click()
   await page.wait_for_selector('.headerBadges >> text=RUNNING')
   await page.locator('.headerKill').click()
   await page.wait_for_selector('.headerKill:disabled')
   killed=await terminal()
   assert killed['risk']['kill_switch_active'] and not killed['strategy']['running']
   assert not killed['authorized_quotes']
   page.once('dialog',lambda dialog:dialog.accept())
   await page.get_by_role('button',name='Resume',exact=True).click()
   await page.wait_for_selector('.headerKill:not(:disabled)')
   final=await terminal()
   assert not final['strategy']['running'] and not final['risk']['kill_switch_active']
   report['workflows'].extend(['unsaved settings immutable','invalid settings rejected','reset/save configuration','simulation never deploys','strategy start/manual kill/resume remains stopped'])
  assert not report['page_errors'], report['page_errors']
  report['browser_version']=browser.version
  (output/'browser-report.json').write_text(json.dumps(report,indent=2))
  print(json.dumps({'layout_checks':len(report['layout_checks']),'workflows':report['workflows'],'page_errors':report['page_errors'],'console_errors':len(report['console_errors']),'browser':browser.version},indent=2))
  await browser.close()

if __name__=='__main__':
 parser=argparse.ArgumentParser()
 parser.add_argument('--url',default='http://127.0.0.1:5173')
 parser.add_argument('--chromium',default='/usr/bin/chromium')
 parser.add_argument('--output',default='../work/phase131/browser')
 parser.add_argument('--paper-controls',action='store_true')
 asyncio.run(main(parser.parse_args()))
