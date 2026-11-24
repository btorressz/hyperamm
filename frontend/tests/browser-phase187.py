"""Financial evidence and accessibility acceptance over the existing browser fixture."""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re
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
    portfolio = None
    portfolio_url = "**/portfolio-research/terminal"

    async def portfolio_result(route):
        nonlocal portfolio
        response = await route.fetch()
        assert response.status == 200, await response.text()
        portfolio = await response.json()
        await route.fulfill(response=response)

    await page.route(portfolio_url, portfolio_result)
    try:
        async with page.expect_response(lambda r: r.url.endswith("/portfolio-research/terminal")) as portfolio_response:
            await content.get_by_role("button", name="Analyze portfolio", exact=True).click()
        assert (await portfolio_response.value).status == 200
    finally:
        await page.unroute(portfolio_url, portfolio_result)
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


async def audit4_hd_details(page, report, choose_mode, capture, passed):
    await choose_mode("Pro")
    markets = page.get_by_role("region", name="Discovered markets")
    search = markets.get_by_role("searchbox", name="Market or DEX")
    details = markets.get_by_role("region", name="Selected market details")
    summary_url = "**/market-universe/market-summaries"
    refresh_observations = page.get_by_role("button", name="Refresh observations")
    core = "HYPERLIQUID:MAINNET:CORE_PERP::BTC"
    hip = "HYPERLIQUID:MAINNET:HIP3_PERP:io:AAPL"
    batches = []
    metrics = ("mark_price", "oracle_price", "previous_day_price", "funding_rate", "day_notional_volume",
               "open_interest_base", "mark_change_vs_previous_day_percent")

    def record(request):
        if request.url.endswith("/market-universe/market-summaries"):
            batches.append(request.post_data_json)

    page.on("request", record)

    def card(symbol):
        return markets.get_by_role("article").filter(has=page.get_by_role("heading", name=symbol, exact=True))

    def value(term, region=details):
        return region.locator("dl > div").filter(has=page.get_by_text(term, exact=True)).locator("dd")

    def is_summary(request):
        return request.url.endswith("/market-universe/market-summaries")

    async def select(symbol):
        await card(symbol).get_by_role("button", name=f"Details for {symbol}").click()
        await expect(details.get_by_role("heading", name=f"{symbol} details")).to_be_visible()

    async def assert_values(mark, rate, status="Current"):
        await expect(value("Observation status")).to_have_text(status)
        await expect(value("Mark price")).to_have_text(mark)
        await expect(value("Funding / hour")).to_have_text(rate)

    btc = card("BTC")
    await expect(value("Mark price", btc)).to_have_text("65,012.5")
    button = btc.get_by_role("button", name="Details for BTC")
    await button.focus()
    await page.keyboard.press("Enter")
    await expect(button).to_be_focused()
    await expect(button).to_have_attribute("aria-pressed", "true")
    await assert_values("65,012.5", "-0.01%")
    await expect(value("Funding interval")).to_have_text("1 hour")
    await expect(value("Provider event time")).to_have_text("Unavailable")
    await expect(value("Price units")).to_contain_text("denomination not independently verified")
    await expect(value("Server receipt time").locator("time")).to_have_attribute("datetime", re.compile(r"^\d{4}-"))
    await expect(btc.get_by_role("button", name="Open Research for BTC")).to_be_enabled()
    passed("Keyboard-selected Core Details and card agree on mark, hourly percent and the source clock")

    aapl = card("io:AAPL")
    await expect(value("Funding / hour", aapl)).to_have_text("0.0125%")
    display_mark = await value("Mark price", aapl).inner_text()
    await select("io:AAPL")
    async with page.expect_request(lambda req: is_summary(req) and hip in req.post_data_json["market_keys"]) as filtered:
        await search.fill("DOGE")
    assert len((await filtered.value).post_data_json["market_keys"]) == 2
    await expect(aapl).to_have_count(0)
    await assert_values(display_mark, "0.0125%")
    await expect(value("Mark price")).to_have_attribute("title", "219.123456789123456789")
    await expect(value("Canonical market")).to_have_text(hip)
    await expect(value("Observation source")).to_have_text("Hyperliquid public Info · metaAndAssetCtxs")
    await search.fill("")
    await expect(aapl).to_be_visible()
    async with page.expect_request(lambda req: is_summary(req) and hip in req.post_data_json["market_keys"]) as paged:
        await markets.get_by_role("button", name="Next").click()
    page_keys = (await paged.value).post_data_json["market_keys"]
    assert hip in page_keys and len(page_keys) == 13
    await expect(aapl).to_have_count(0)
    await markets.get_by_role("combobox", name="Sort by").select_option("funding_rate")
    await assert_values(display_mark, "0.0125%")
    await search.fill("DOGE")
    await assert_values(display_mark, "0.0125%")
    async with page.expect_response(lambda res: is_summary(res.request) and res.request.post_data_json["refresh"]) as refresh:
        await refresh_observations.click()
    wire = await (await refresh.value).json()
    assert wire["read_only"] and not wire["execution_eligible"] and wire["authority"] == "NONE"
    await assert_values(display_mark, "0.0125%")
    discovery_requested, release_discovery = asyncio.Event(), asyncio.Event()

    async def checking_catalog(route):
        discovery_requested.set()
        await release_discovery.wait()
        await route.continue_()

    await page.route("**/market-universe", checking_catalog)
    try:
        await page.get_by_role("button", name="Refresh discovery").click()
        await asyncio.wait_for(discovery_requested.wait(), 10)
        await assert_values("Unavailable", "Unavailable", "Updating")
    finally:
        release_discovery.set()
    await assert_values(display_mark, "0.0125%")
    await page.unroute("**/market-universe", checking_catalog)
    await capture("audit4-hd-selected-off-page", ".marketExplorer", anchor=details)
    assert all(1 <= len(batch["market_keys"]) <= 13 for batch in batches)
    passed("AAPL stays qualified across search, pagination, page-local sort, refresh and all Explorer layouts")

    def timestamp(value):
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")

    async def replace_summary(route, *, error=None, expiry=False, network=None, catalog=None):
        response = await route.fetch()
        wire = await response.json()
        if network is not None:
            wire["network"] = network
        if catalog is not None:
            wire["catalog_fingerprint"] = catalog
        for row in wire["results"]:
            if row["identity"]["dex"] != "io" or row["status"] != "CURRENT":
                continue
            if error:
                row.update(dict.fromkeys(metrics))
                row.update(status="ERROR", error=error, observed_at=None, valid_until=None,
                           observation_fingerprint=None)
            if expiry:
                row["valid_until"] = min(row["valid_until"], timestamp(datetime.now(timezone.utc) + timedelta(seconds=1.5)))
                payload = {k: v for k, v in row.items() if k != "observation_fingerprint"}
                payload["catalog_fingerprint"] = wire["catalog_fingerprint"]
                row["observation_fingerprint"] = sha256(
                    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
                ).hexdigest()
        await route.fulfill(response=response, json=wire)

    for options, status in (
        ({"error": "RATE_LIMITED"}, "Provider rate limit"),
        ({"error": "TIMEOUT"}, "Provider timeout"),
        ({"network": "TESTNET"}, "Invalid market observations. Refresh discovery and try again."),
        ({"catalog": "f" * 64}, "Invalid market observations. Refresh discovery and try again."),
        ({"expiry": True}, "Stale"),
    ):
        async def alter(route):
            await replace_summary(route, **options)
        await page.route(summary_url, alter)
        await refresh_observations.click()
        if options.get("expiry"):
            await assert_values(display_mark, "0.0125%")
        await assert_values("Unavailable", "Unavailable", status)
        await page.unroute(summary_url, alter)
    passed("Off-page Details retire values on 429, timeout, wrong network, wrong catalog and receipt expiry")

    arrived, release, done = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def hold_previous(route):
        if set(route.request.post_data_json["market_keys"]) != {hip, core}:
            await route.continue_()
            return
        response = await route.fetch()
        arrived.set()
        try:
            await release.wait()
            await route.fulfill(response=response)
        except Exception as exc:
            if "aborted" not in str(exc).lower() and "canceled" not in str(exc).lower():
                raise
        finally:
            done.set()

    await page.route(summary_url, hold_previous)
    await search.fill("BTC")
    try:
        await asyncio.wait_for(arrived.wait(), 10)
        await select("BTC")
        await assert_values("65,012.5", "-0.01%")
    finally:
        release.set()
    await asyncio.wait_for(done.wait(), 10)
    await page.unroute(summary_url, hold_previous)
    await assert_values("65,012.5", "-0.01%")
    await expect(value("Canonical market")).to_have_text(core)
    passed("Late HIP-3 data cannot replace a newly selected Core market")

    for symbol, mark, rate, status in (
        ("MISSINGMARK", "Unavailable", "0%", "Current"),
        ("MISSINGFUNDING", "201", "Unavailable", "Current"),
        ("INVALIDFUNDING", "202", "Unavailable", "Current"),
        ("OLD", "Unavailable", "Unavailable", "Unsupported"),
    ):
        await search.fill(symbol)
        await select(symbol)
        await assert_values(mark, rate, status)
    await expect(card("OLD").get_by_role("button", name="Open Research for OLD")).to_be_disabled()
    passed("Delisted and partial Details preserve genuine zero and omit missing or out-of-bound funding")

    await search.fill("io:AAPL")
    await select("io:AAPL")
    await assert_values(display_mark, "0.0125%")
    generation = await value("Catalog fingerprint").inner_text()
    generation_requested = asyncio.Event()
    resume_discovery = asyncio.Event()

    async def hold_discovery(route):
        generation_requested.set()
        await resume_discovery.wait()
        await route.continue_()

    await page.route("**/market-universe", hold_discovery)
    try:
        await asyncio.wait_for(generation_requested.wait(), 35)
        await assert_values("Unavailable", "Unavailable", "Stale catalog")
        await expect(aapl.get_by_role("button", name="Open Research for io:AAPL")).to_be_disabled()
    finally:
        resume_discovery.set()
    await expect(value("Catalog fingerprint")).not_to_have_text(generation)
    await page.unroute("**/market-universe", hold_discovery)
    await assert_values(display_mark, "0.0125%")
    await expect(aapl.get_by_role("button", name="Open Research for io:AAPL")).to_be_enabled()
    passed("Catalog expiry retires Details values and Research handoff until a new discovery generation arrives")

    base = await page.evaluate("({width: innerWidth, dpr: devicePixelRatio})")
    settings = await page.context.new_page()
    await settings.goto("chrome://settings/appearance")
    await settings.get_by_role("combobox", name="Page zoom").select_option("2")
    await settings.close()
    await page.bring_to_front()
    await page.wait_for_function("dpr => devicePixelRatio === dpr * 2", arg=base["dpr"])
    report["zoom_200"] = await page.evaluate(
        "({width: innerWidth, document: document.documentElement.scrollWidth, dpr: devicePixelRatio})",
    )
    assert abs(report["zoom_200"]["width"] * 2 - base["width"]) <= 2
    assert report["zoom_200"]["document"] <= report["zoom_200"]["width"] + 1
    await assert_values(display_mark, "0.0125%")
    report["summary_batches"] = batches
    report["max_summary_keys"] = max(len(batch["market_keys"]) for batch in batches)
    passed("Selected Details keeps both metrics at actual 200% Chromium zoom without horizontal overflow")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    explorer.add_arguments(parser)
    parser.add_argument("--engine", choices=("chromium", "firefox", "webkit"), default="chromium")
    parser.add_argument("--audit4-hd", action="store_true")
    args = parser.parse_args()
    if args.audit4_hd:
        explorer.run_suite(args, audit4_hd_details, backend_app="browser-phase182:audit4_hd_fixture_app")
        return
    explorer.run_suite(args, acceptance, backend_app="browser-phase182:phase187_fixture_app", extra_writes=(
        "/historical-replay/run", "/portfolio-research/preview", "/portfolio-research/terminal",
    ))


if __name__ == "__main__":
    main()
