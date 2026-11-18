"""Audit 3.0 browser measurements against a running local DEMO/PAPER app."""
import argparse
import asyncio
import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.async_api import async_playwright

SIZES = [(1920, 1080), (1440, 1000), (1024, 768), (768, 900), (390, 844)]
ROUTES = ("dashboard", "markets", "strategy", "amm-settings", "execution", "risk",
          "agents", "vault", "analytics", "simulation", "portfolio-research", "logs", "settings")
TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]
SELECTORS = {
    "dashboard": [".bookHeader"],
    "strategy": [".gaugeLabels", ".inventoryState small", ".perpPositionHead span"],
    "risk": [".riskHero small", ".riskList p", ".riskFirewallGrid span", ".referencePanel th"],
    "agents": [".researchWorkspace .panelHead span", ".researchEventList time"],
}

CONTRAST = r"""(selectors) => selectors.flatMap(selector => {
  const rgba = css => css.match(/[\d.]+/g).map(Number);
  const lum = rgb => rgb.slice(0, 3).map(x => {
    const norm = x / 255;
    return norm <= 0.04045 ? norm / 12.92 : ((norm + 0.055) / 1.055) ** 2.4;
  }).reduce((sum, val, i) => sum + val * [0.2126, 0.7152, 0.0722][i], 0);
  return [...document.querySelectorAll(selector)].filter(e =>
    e.getClientRects().length && e.textContent.trim()).map(e => {
    const style = getComputedStyle(e);
    const fg = rgba(style.color);
    let path = [];
    for (let p = e; p; p = p.parentElement) {
      const css = getComputedStyle(p);
      if (css.backgroundImage !== 'none' || Number(css.opacity) !== 1)
        throw Error('Manual background measurement required for ' + selector);
      const paint = rgba(css.backgroundColor);
      path.unshift(paint);
      if ((paint[3] ?? 1) === 1) break;
    }
    const blend = (under, paint) => under.map((c,i) => c * (1 - (paint[3] ?? 1)) + paint[i] * (paint[3] ?? 1));
    const bg = path.reduce(blend, [255, 255, 255]);
    const levels = [lum(blend(bg, fg)), lum(bg)].sort((a,b) => b-a);
    return {selector, foreground: style.color, background: bg, font: style.fontSize,
            ratio: (levels[0] + .05) / (levels[1] + .05)};
  });
})"""


async def keyboard_region(page, name, axis):
    target = page.get_by_role("region", name=name, exact=True)
    await page.locator("#page-content").focus()
    for tab_count in range(1, 100):
        await page.keyboard.press("Tab")
        if await target.evaluate("e => document.activeElement === e"):
            break
    else:
        raise AssertionError(f"Tab could not reach {name}")
    assert await target.evaluate("""e => e.matches(':focus-visible') &&
        getComputedStyle(e).outlineStyle !== 'none' && parseFloat(getComputedStyle(e).outlineWidth) >= 2""")
    position = "scrollLeft" if axis == "horizontal" else "scrollTop"
    before = await target.evaluate("(e,key) => e[key]", position)
    await page.keyboard.press("ArrowRight" if axis == "horizontal" else "ArrowDown")
    await page.wait_for_function("([name,key,pos]) => document.activeElement?.ariaLabel === name && document.activeElement[key] > pos",
                                 arg=[name, position, before])
    return {"region": name, "tabs": tab_count, "axis": axis,
            "pixels": await target.evaluate("(e,key) => e[key]", position) - before}


async def audit(page):
    return await page.evaluate("""async tags => {
      const result = await axe.run({runOnly: {type:'tag', values:tags}, resultTypes:['violations','incomplete']});
      const items = rows => rows.map(r => ({rule:r.id, nodes:r.nodes.map(n => n.target.join(' '))}));
      return {version:result.testEngine.version, violations:items(result.violations), manual:items(result.incomplete)};
    }""", TAGS)


async def run(args, scratch, report):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch_persistent_context(
            scratch / "profile", executable_path=args.chromium, headless=True,
            args=["--no-sandbox"],
        )
        page = browser.pages[0]
        report["browser"] = (await (await browser.new_cdp_session(page)).send("Browser.getVersion"))["product"]
        page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
        page.on("console", lambda message: report["console_errors"].append(message.text)
                if message.type == "error" else None)
        await page.goto(args.url + "/#/dashboard")
        await page.get_by_role("heading", name="Liquidity terminal").wait_for()
        assert await page.locator("html").get_attribute("lang") == "en"
        await page.add_script_tag(path=args.axe)

        async def route(slug):
            await page.evaluate("slug => location.hash = '#/' + slug", slug)
            await page.wait_for_function("slug => location.hash === '#/' + slug", arg=slug)
            await page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")

        await route("markets")
        await page.get_by_role("heading", name="Market microstructure").wait_for()
        await page.get_by_role("region", name="Venue & perpetual context").wait_for()
        await route("amm-settings")
        factor = page.get_by_label("Concentration factor", exact=True)
        original = await factor.input_value()
        for value in ("9" if original != "9" else "8", original):
            await factor.fill(value)
            async with page.expect_response(lambda r: r.url.endswith("/api/v1/strategy") and r.request.method == "PUT") as pending:
                await page.get_by_role("button", name="Save", exact=True).click()
            response = await pending.value
            assert response.ok, await response.text()
            assert str((await response.json())["config"]["concentration_factor"]) == value

        # Actual DEMO strategy data produces retained agent events and a
        # reference snapshot after the configuration transition resets them.
        await route("agents")
        response = await page.request.post(args.url + "/api/v1/strategy/start")
        assert response.status == 200, await response.text()
        async with asyncio.timeout(20):
            while True:
                response = await page.request.get(args.url + "/api/v1/agents/events?limit=100")
                assert response.ok, await response.text()
                if await response.json():
                    break
                await asyncio.sleep(0.2)
        await page.get_by_role("button", name="Refresh retained events").click()
        await page.get_by_role("region", name="Recent agent events").wait_for()
        response = await page.request.post(args.url + "/api/v1/strategy/stop")
        assert response.ok, await response.text()
        report["workflows"] = ["Current DEMO/PAPER terminal", "Operational market evidence",
                               "AMM configuration PUT and restore", "Retained risk and agent evidence"]

        for width, height in SIZES:
            await page.set_viewport_size({"width": width, "height": height})
            for slug in ROUTES if width in (1440, 390) else ("risk", "agents"):
                await route(slug)
                if slug == "agents":
                    await page.get_by_role("region", name="Recent agent events").wait_for()
                assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), (slug, width)
                result = await audit(page)
                report["routes"].append({"route": slug, "viewport": [width, height], **result})
                print(width, slug, result["violations"], flush=True)
                if slug in SELECTORS:
                    colors = await page.evaluate(CONTRAST, SELECTORS[slug])
                    unique = {json.dumps(color, sort_keys=True): color for color in colors}
                    report["contrast"].append({"route": slug, "viewport": [width, height],
                                               "samples": list(unique.values())})
                if slug == "risk" or (slug == "agents" and width in (1440, 390)):
                    region = page.get_by_role("region", name="Reference source evidence table" if slug == "risk"
                                              else "Recent agent events", exact=True)
                    await region.evaluate("e => e.scrollIntoView({block:'center'})")
                    shot = f"{slug}-{width}.png"
                    await page.screenshot(path=args.output / shot)
                    report["screenshots"].append({"route": slug, "viewport": [width, height], "file": shot})

        await route("risk")
        report["keyboard"].append(await keyboard_region(page, "Reference source evidence table", "horizontal"))
        await route("agents")
        events = page.get_by_role("region", name="Recent agent events", exact=True)
        assert await events.get_by_role("list").count()
        assert await events.get_by_role("listitem").count()
        report["keyboard"].append(await keyboard_region(page, "Recent agent events", "vertical"))

        await page.set_viewport_size({"width": 1440, "height": 1000})
        await route("risk")
        base = await page.evaluate("({width:innerWidth, height:innerHeight, dpr:devicePixelRatio})")
        settings = await browser.new_page()
        await settings.goto("chrome://settings/appearance")
        zoom_selector = settings.get_by_role("combobox", name="Page zoom")
        await zoom_selector.select_option(value="2")
        zoom = float(await zoom_selector.input_value())
        await settings.close()
        await page.bring_to_front()
        await page.wait_for_function("dpr => devicePixelRatio === dpr * 2", arg=base["dpr"])
        actual = await page.evaluate("({width:innerWidth, height:innerHeight, dpr:devicePixelRatio, scroll:document.documentElement.scrollWidth})")
        report["zoom"] = {"browser_factor": zoom, "before": base, "after": actual, **await audit(page)}
        report["zoom"]["contrast"] = await page.evaluate(CONTRAST, [".mobileNavToggle", ".referencePanel th"])
        assert zoom == 2 and abs(actual["width"] * 2 - base["width"]) <= 2
        assert actual["scroll"] <= actual["width"] + 1
        await page.get_by_role("region", name="Reference source evidence table").evaluate(
            "e => e.scrollIntoView({block:'start', behavior:'instant'})")
        await page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
        devtools = await browser.new_cdp_session(page)
        frame = await devtools.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        (args.output / "risk-zoom-200.png").write_bytes(base64.b64decode(frame["data"]))
        report["screenshots"].append({"route":"risk", "viewport":[actual["width"], actual["height"]],
                                      "file":"risk-zoom-200.png", "zoom":zoom})
        await browser.close()


async def main(args):
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"rules": TAGS, "routes": [], "contrast": [], "keyboard": [],
              "screenshots": [], "page_errors": [], "console_errors": []}
    try:
        with TemporaryDirectory(prefix="hyperamm-accessibility-") as directory:
            await run(args, Path(directory), report)
        assert not report["page_errors"], report["page_errors"]
        assert not report["console_errors"], report["console_errors"]
        assert not any(r["violations"] for r in report["routes"] + [report["zoom"]])
        assert report["contrast"] and all(s["ratio"] >= 4.5 for r in report["contrast"] for s in r["samples"])
        assert report["zoom"]["contrast"] and all(s["ratio"] >= 4.5 for s in report["zoom"]["contrast"])
    finally:
        (args.output / "accessibility.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5173")
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    parser.add_argument("--axe", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    asyncio.run(main(parser.parse_args()))
