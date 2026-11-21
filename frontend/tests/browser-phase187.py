"""Financial evidence and accessibility acceptance over the existing browser fixture."""
import argparse
import asyncio
from importlib import import_module

from playwright.async_api import expect

explorer = import_module("browser-phase186")
audit = import_module("browser-audit3-accessibility")
BASE = explorer.BASE
LAYOUTS = (*explorer.VIEWPORTS, (668, 390))
ROUTES = {
    "dashboard": "Liquidity terminal",
    "markets": "Market Explorer",
    "strategy": "Current virtual pool & authorization",
    "amm-settings": "AMM Settings",
    "execution": "Execution",
    "risk": "Risk Management",
    "agents": "Agent intelligence workspace",
    "vault": "Research vault & accounting",
    "analytics": "Session analytics",
    "simulation": "Simulation & Optimization",
    "portfolio-research": "Portfolio Research",
    "logs": "Operational logs & diagnostics",
    "settings": "Settings & system configuration",
}


async def route_matrix(page, report, choose_mode, open_route):
    content = page.locator("#page-content")
    navigation = page.get_by_role("navigation", name="Terminal pages")
    report["routes"] = {}
    for mode in ("Starter", "Pro", "Institutional"):
        await choose_mode(mode)
        report["routes"][mode] = []
        for slug in ROUTES:
            await open_route(slug)
            selected = navigation.locator(f'a[href="#/{slug}"]')
            await expect(selected).to_have_attribute("aria-current", "page")
            await page.reload()
            await expect(selected).to_have_attribute("aria-current", "page")
            await expect(content.get_by_text(ROUTES[slug], exact=True).first).to_be_visible()
            await expect(page.get_by_role("button", name=mode, exact=True)).to_have_attribute("aria-pressed", "true")
            report["routes"][mode].append(slug)
    await page.go_back()
    await expect(page).to_have_url(f"{BASE}/#/logs")
    await expect(content).to_be_focused()
    await page.wait_for_function("scrollY === 0")
    await page.go_forward()
    await expect(page).to_have_url(f"{BASE}/#/settings")
    await expect(content).to_be_focused()


async def acceptance(page, report, choose_mode, capture, passed):
    content = page.locator("#page-content")

    async def open_route(slug):
        url = f"{BASE}/#/{slug}"
        await page.goto(url)
        await expect(page).to_have_url(url)
        await expect(content.get_by_text(ROUTES[slug], exact=True).first).to_be_visible()

    await choose_mode("Institutional")
    await open_route("markets")
    markets = content.get_by_role("region", name="Discovered markets")
    await expect(markets.get_by_role("article").filter(has=page.get_by_role("heading", name="xyz:UNKNOWN", exact=True))
                 .get_by_text("0.0000012", exact=True)).to_be_visible()
    await expect(markets.get_by_role("article").filter(has=page.get_by_role("heading", name="missing:GOLD", exact=True))
                 .locator(".explorerObservation").get_by_text("Unavailable", exact=True)).to_be_visible()

    await open_route("risk")
    # As in the Audit 3.0 harness, seed retained evidence using only the
    # isolated DEMO/PAPER runtime before exercising the read-only table.
    response = await page.request.post(f"{BASE}/api/v1/strategy/start")
    assert response.ok, await response.text()
    try:
        await expect(page.get_by_role("region", name="Reference source evidence table")).to_be_visible()
    finally:
        response = await page.request.post(f"{BASE}/api/v1/strategy/stop")
        assert response.ok, await response.text()
    await capture("risk-firewall", "main", anchor=content.get_by_text("Risk Management", exact=True), viewports=LAYOUTS)
    report["contrast"] = await page.evaluate(audit.CONTRAST, [".marketTitle", ".marketTitle span", ".riskHero strong", ".riskList b"])
    await page.set_viewport_size({"width": 390, "height": 844})
    report["contrast"] += await page.evaluate(audit.CONTRAST, [".mobileNavToggle > span"])
    assert report["contrast"] and all(sample["ratio"] >= 4.5 for sample in report["contrast"])
    report["keyboard"] = [await audit.keyboard_region(page, "Reference source evidence table", "horizontal")]
    open_nav = page.get_by_role("button", name="Open navigation")
    await open_nav.focus()
    await page.keyboard.press("Space")
    drawer = page.get_by_role("dialog", name="Terminal navigation")
    await expect(drawer.get_by_role("link", name="Risk", exact=True)).to_be_focused()
    first = drawer.get_by_role("button", name="Close navigation")
    last = drawer.get_by_role("link").last
    await first.focus()
    await page.keyboard.press("Shift+Tab")
    await expect(last).to_be_focused()
    await page.keyboard.press("Tab")
    await expect(first).to_be_focused()
    await page.keyboard.press("Escape")
    await expect(drawer).to_be_hidden()
    await expect(open_nav).to_be_focused()
    await page.set_viewport_size({"width": 1440, "height": 1000})
    await open_route("agents")
    await capture("supervisory-agents", "main", anchor=content.get_by_role("heading", name=ROUTES["agents"]),
                  viewports=LAYOUTS)
    passed("Narrow financial table keyboard scrolling, drawer focus containment and focus return")

    await choose_mode("Pro")
    await page.goto(f"{BASE}/#/simulation/paper")
    paper = content.get_by_role("region", name="Generalized PAPER research")
    market = paper.get_by_role("combobox", name="Discovered perpetual")
    await market.select_option("HYPERLIQUID:MAINNET:HIP3_PERP:xyz:GOLD")
    await paper.get_by_role("textbox", name="Synthetic reference price").fill("2500")
    await paper.get_by_role("combobox", name="PAPER research mode").select_option("asset")
    config = paper.get_by_role("group", name="Asset-aware AMM configuration")
    await config.get_by_role("combobox", name="AMM model").select_option("CONCENTRATED")
    await config.get_by_role("combobox", name="Research asset family").select_option("COMMODITY")
    check = paper.get_by_role("button", name="Check PAPER eligibility")
    run = paper.get_by_role("button", name="Run local PAPER")
    await check.click()
    await expect(run).to_be_enabled()
    result = paper.get_by_role("region", name="PAPER result evidence")

    sent, release = asyncio.Event(), asyncio.Event()

    async def defer_result(route):
        response = await route.fetch()
        assert response.status == 200
        sent.set()
        await release.wait()
        await route.fulfill(response=response)

    await page.route("**/generalized-paper/run", defer_result)
    try:
        await run.click()
        await asyncio.wait_for(sent.wait(), 20)
        await expect(paper.get_by_role("status").filter(has_text="Running local PAPER")).to_be_visible()
        await open_route("markets")
        await choose_mode("Institutional")
    finally:
        release.set()
        await page.unroute_all(behavior="wait")
    await page.goto(f"{BASE}/#/simulation/paper")
    await expect(result.get_by_role("status")).to_contain_text("xyz:GOLD")
    await result.get_by_text("Asset-aware AMM configuration and provenance", exact=True).click()
    await expect(result.get_by_text("Concentrated Liquidity", exact=True)).to_be_visible()
    await expect(result.get_by_text("Ending simulated equity", exact=True)).to_be_visible()
    await expect(result.get_by_text("Funding in hypothetical quote units", exact=True)).to_be_visible()
    await capture("asset-aware-paper", "main", anchor=result, viewports=LAYOUTS)
    assert sum(path.endswith("/generalized-paper/run") for path in report["writes"]) == 2
    passed("Qualified HIP-3 concentrated PAPER completes across page and mode changes with a single admission")

    await page.goto(f"{BASE}/#/simulation/replay")
    await expect(content.get_by_role("heading", name="Historical Replay Studio")).to_be_visible()
    await content.get_by_role("combobox", name="Historical dataset").select_option("BTC-complete-fixture")
    async with page.expect_response(lambda r: r.url.endswith("/historical-replay/run")) as replay_response:
        await content.get_by_role("button", name="Run Historical PAPER Replay").click()
    assert (await replay_response.value).status == 200
    replay = content.get_by_role("heading", name="Segment-only PAPER results")
    await expect(replay).to_be_visible()
    book = content.get_by_role("region", name="Historical retained L2 book")
    await expect(book.locator("thead th[scope=col]")).to_have_count(3)
    groups = book.locator("tbody")
    await expect(groups).to_have_count(2)
    for index, side in enumerate(("Asks", "Bids")):
        group = groups.nth(index)
        await expect(group.locator("th[scope=rowgroup]")).to_have_text(side)
        await expect(group.get_by_role("cell").first).to_be_visible()
    await capture("historical-replay", "main", anchor=replay, viewports=LAYOUTS)

    await open_route("portfolio-research")
    await page.get_by_label("Frames per market", exact=True).fill("12")
    await content.get_by_role("button", name="Validate / Preview", exact=True).click()
    async with page.expect_response(lambda r: r.url.endswith("/portfolio-research/terminal")) as portfolio_response:
        await content.get_by_role("button", name="Analyze portfolio", exact=True).click()
    response = await portfolio_response.value
    assert response.status == 200, await response.text()
    portfolio = await response.json()
    assert portfolio["authority"] == "NONE"
    assert [row["market"] for row in portfolio["baseline"]["markets"]] == ["BTC", "ETH", "SOL"]
    sections = content.get_by_role("navigation", name="Portfolio workspace sections")
    await sections.get_by_role("button", name="Analytics", exact=True).click()
    analytics = content.get_by_role("heading", name="Baseline Portfolio Analytics", exact=True)
    await expect(analytics).to_be_visible()
    await capture("portfolio-research", "main", anchor=analytics, viewports=LAYOUTS)
    await sections.get_by_role("button", name="Provenance", exact=True).click()
    provenance = content.get_by_role("region", name="Provenance & Diagnostics")
    await expect(provenance.get_by_text("Configuration fingerprint", exact=True)).to_be_visible()
    await expect(provenance).to_be_visible()
    await capture("portfolio-provenance", "main", anchor=provenance, viewports=LAYOUTS)
    passed("Generated Historical Replay and real native portfolio analytics and source receipts on six layouts")

    await choose_mode("Pro")
    await page.goto(f"{BASE}/#/simulation/paper")
    await paper.get_by_role("combobox", name="PAPER research mode").select_option("standard")
    price = paper.get_by_role("textbox", name="Synthetic reference price")
    await price.fill("2500.123")
    async with page.expect_response(lambda r: r.url.endswith("/generalized-paper/eligibility")) as rejected:
        await check.click()
    assert (await rejected.value).status == 422
    await expect(paper.get_by_text("PRICE_UNREPRESENTABLE", exact=True)).to_be_visible()
    await expect(run).to_be_disabled()
    await price.fill("2500")

    path = "**/generalized-paper/run"
    report["paper_failures"] = [422]
    for status, message in ((429, "The shared PAPER worker is busy"),
                            (500, "The local PAPER request failed"),
                            (503, "The shared PAPER worker is unavailable"),
                            (504, "The local PAPER request failed")):
        await check.click()
        await expect(run).to_be_enabled()

        async def failed(route):
            await route.fulfill(status=status, json={"detail": "injected local fixture detail"})

        await page.route(path, failed)
        requests_before = report["writes"].count("/api/v1/generalized-paper/run")
        try:
            await run.click()
            await expect(paper.get_by_role("alert").filter(has_text=message)).to_be_visible()
            await expect(paper.get_by_text("injected local fixture detail", exact=False)).to_have_count(0)
            await expect(run).to_be_disabled()
            await expect(result).to_have_count(0)
            assert report["writes"].count("/api/v1/generalized-paper/run") == requests_before + 1
            report["paper_failures"].append(status)
        finally:
            await page.unroute(path, failed)

    await check.click()
    await expect(run).to_be_enabled()

    async def interrupted(route):
        await route.abort("internetdisconnected")

    await page.route(path, interrupted)
    await run.click()
    await expect(paper.get_by_role("alert")).to_be_visible()
    await expect(run).to_be_disabled()
    await page.unroute(path, interrupted)
    await check.click()
    await expect(run).to_be_enabled()
    await run.click()
    await expect(result.get_by_role("status")).to_contain_text("xyz:GOLD")
    passed("Actual 422 and injected 429, 500, 503, 504 and network interruption retire admission and allow manual recovery")

    terminal_blocked = True

    async def terminal(socket):
        if terminal_blocked:
            await socket.close(code=1013)
        else:
            socket.connect_to_server()

    await page.route_web_socket("**/ws/terminal", terminal)
    await page.goto(f"{BASE}/#/risk")
    await page.reload()
    await expect(content.get_by_text("Connecting to HyperAMM…", exact=True)).to_be_visible()
    await expect(content.get_by_text("Risk Management", exact=True)).to_have_count(0)
    await open_route("markets")
    await expect(markets.get_by_role("heading", name="xyz:GOLD", exact=True)).to_be_visible()
    terminal_blocked = False
    await open_route("risk")
    passed("Terminal WebSocket loss preserves read-only Explorer and reconnect restores current risk evidence")

    await route_matrix(page, report, choose_mode, open_route)
    passed("All 13 routes load and refresh in every mode, with active links, back/forward, focus and scroll")
    await open_route("risk")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    explorer.add_arguments(parser)
    parser.add_argument("--engine", choices=("chromium", "firefox", "webkit"), default="chromium")
    args = parser.parse_args()
    explorer.run_suite(args, acceptance, backend_app="browser-phase182:phase187_fixture_app", extra_writes=(
        "/historical-replay/run", "/portfolio-research/preview", "/portfolio-research/terminal",
    ))


if __name__ == "__main__":
    main()
