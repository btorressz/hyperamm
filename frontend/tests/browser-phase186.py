"""Chromium acceptance for the Phase 18.6 presentation and PAPER handoff."""
import argparse
import asyncio
from contextlib import ExitStack
from importlib import import_module
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from playwright.async_api import async_playwright, expect

paper = import_module("browser-phase182")
audit = import_module("browser-audit3-accessibility")
ROOT = paper.ROOT
BASE = "http://127.0.0.1:5173"
VIEWPORTS = ((390, 844), (768, 900), (1024, 768), (1440, 1000), (1920, 1080))
RESEARCH_WRITES = ("/market-universe/advisory", "/market-universe/market-summaries")


async def run(args, profile, report, extension=None, extra_writes=()):
    engine = getattr(args, "engine", "chromium")
    async with async_playwright() as playwright:
        launch = {"headless": True, "viewport": {"width": 1440, "height": 1000}}
        if engine == "chromium":
            launch.update(executable_path=args.chromium, args=["--no-sandbox"])
        context = await getattr(playwright, engine).launch_persistent_context(profile, **launch)
        await context.add_init_script("""(() => document.addEventListener('DOMContentLoaded', () => {
          const style = document.createElement('style');
          style.textContent = 'body::after { content: "DEMO · PROVIDER FIXTURE"; position: fixed; right: 8px; bottom: 8px; z-index: 15; padding: 4px 8px; color: white; background: #18365e; font: 12px sans-serif; pointer-events: none; }';
          document.head.append(style);
        }))()""")
        await context.add_init_script(path=args.axe)
        page = context.pages[0] if context.pages else await context.new_page()
        page.set_default_timeout(12000)
        if engine == "chromium":
            report["browser"] = (await (await context.new_cdp_session(page)).send("Browser.getVersion"))["product"]
        else:
            report["browser"] = await page.evaluate("navigator.userAgent")
        writes = report["writes"]
        page.on("pageerror", lambda err: report["page_errors"].append(str(err)))
        page.on("request", lambda req: writes.append(req.url.removeprefix(BASE))
                if req.method in {"POST", "PUT", "PATCH", "DELETE"} else None)
        await paper.wait_for_fixture(page)
        await page.goto(BASE + "/#/markets")
        modes = page.get_by_role("group", name="Workspace mode")

        def mode(name):
            return modes.get_by_role("button", name=name, exact=True)

        async def choose_mode(name):
            await mode(name).click()
            await expect(mode(name)).to_have_attribute("aria-pressed", "true")
        main = page.get_by_role("main")
        nav = page.get_by_role("navigation", name="Terminal pages")
        markets = page.get_by_role("region", name="Discovered markets")
        search = markets.get_by_role("searchbox", name="Market or DEX")

        def passed(description):
            report["workflows"].append(description)
            print("PASS " + description, flush=True)

        async def route(path, heading):
            await page.evaluate("path => { location.hash = path }", "#/" + path)
            await expect(main.get_by_role("heading", name=heading, exact=True)).to_be_visible()

        async def capture(name, css, *, anchor=None, viewports=VIEWPORTS):
            for width, height in viewports:
                await page.set_viewport_size({"width": width, "height": height})
                await page.evaluate("window.scrollTo(0, 0)")
                await page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                dimensions = await page.evaluate("({viewport: innerWidth, content: document.documentElement.scrollWidth})")
                assert dimensions["content"] <= dimensions["viewport"] + 1, (name, dimensions)
                report["viewports"].append({"workspace": name, "height": height, **dimensions})
                if width in (390, 1440):
                    if anchor is not None:
                        await anchor.evaluate("""e => {
                          e.scrollIntoView({block: 'start', behavior: 'instant'});
                          window.scrollBy(0, -document.querySelector('.topbar').offsetHeight - 12);
                        }""")
                    screenshot = f"{name}-{width}.png"
                    await page.screenshot(path=args.output / screenshot)
                    report["screenshots"].append(screenshot)
                    scope = await page.evaluate("""async ({css, tags}) => {
                      const result = await axe.run(css, {runOnly: {type:'tag', values:tags},
                        resultTypes: ['violations', 'incomplete']});
                      const rows = list => list.map(v => ({rule:v.id, nodes:v.nodes.map(n=>n.target)}));
                      return {violations: rows(result.violations), manual: rows(result.incomplete)};
                    }""", {"css": css, "tags": audit.TAGS})
                    report["axe"].append({"workspace": name, "width": width, **scope})
            await page.set_viewport_size({"width": 1440, "height": 1000})

        if getattr(args, "audit4_hd", False):
            await extension(page, report, choose_mode, capture, passed)
            assert not report["page_errors"], report["page_errors"]
            assert all(url.endswith("/market-universe/market-summaries") for url in writes), writes
            assert not any(row["violations"] for row in report["axe"]), report["axe"]
            await context.close()
            return

        await expect(markets.get_by_text("6 of 6 discovered markets")).to_be_visible()
        await expect(markets.get_by_role("heading", name="BTC", exact=True)).to_be_visible()
        await expect(markets.get_by_role("heading", name="xyz:GOLD", exact=True)).to_be_visible()
        btc = markets.get_by_role("article").filter(has=page.get_by_role("heading", name="BTC", exact=True))
        await expect(btc.get_by_text("65,012.5", exact=True)).to_be_visible()
        await expect(btc.get_by_text("Funding / hour", exact=True)).to_be_visible()
        await expect(btc.get_by_text("-0.01%", exact=True)).to_be_visible()
        await expect(btc.get_by_text("1.2M", exact=True)).to_be_visible()
        await expect(btc.get_by_text("130.5", exact=True)).to_be_visible()
        await markets.get_by_role("combobox", name="Sort by").select_option("mark_price")
        await expect(markets.get_by_role("article").nth(0).get_by_role("heading", name="BTC", exact=True)).to_be_visible()
        await expect(markets.get_by_role("article").nth(1).get_by_role("heading", name="xyz:GOLD", exact=True)).to_be_visible()
        await markets.get_by_role("combobox", name="Sort by").select_option("alphabetical")
        await markets.get_by_role("button", name="Details for xyz:GOLD").click()
        details = markets.get_by_role("region", name="Selected market details")
        await expect(details.get_by_text("2,402.5", exact=True)).to_be_visible()
        await expect(details.get_by_text("Hyperliquid public Info · metaAndAssetCtxs", exact=True)).to_be_visible()
        await markets.get_by_role("button", name="Details for xyz:GOLD").click()
        await search.fill("gold")
        await expect(markets.get_by_text("2 of 6 discovered markets")).to_be_visible()
        await search.fill("xyz")
        await expect(markets.get_by_text("2 of 6 discovered markets")).to_be_visible()
        await markets.get_by_role("combobox", name="Instrument type").select_option("CORE_PERP")
        await expect(markets.get_by_text("No markets match your filters.")).to_be_visible()
        await markets.get_by_role("button", name="Clear filters").click()
        await markets.get_by_role("combobox", name="Research").select_option("unsupported")
        await expect(markets.get_by_text("1 of 6 discovered markets")).to_be_visible()
        await expect(markets.get_by_role("button", name="Open Research for OLD")).to_be_disabled()
        await markets.get_by_role("button", name="Clear filters").click()
        await markets.get_by_role("button", name="Details for missing:GOLD").click()
        await expect(markets.get_by_text("HYPERLIQUID:MAINNET:HIP3_PERP:missing:GOLD", exact=True)).to_be_visible()
        await markets.get_by_role("button", name="Details for missing:GOLD").click()
        passed("Core, HIP-3, symbol and DEX search, filters, missing observations, delisting and qualified details")

        async def large_catalog(route):
            response = await route.fetch()
            wire = await response.json()
            records = wire["catalog"]["records"]
            original = records[0]
            decision = wire["eligibility"][0]
            pairs = list(zip(records, wire["eligibility"], strict=True))
            for index in range(2000):
                symbol = f"TEST{index:04}"
                identity = {**original["identity"], "instrument_name": symbol}
                pairs.append(({**original, "identity": identity, "source_coin": symbol, "universe_index": index + 3},
                              {**decision, "identity": identity}))
            pairs.sort(key=lambda pair: (pair[0]["identity"]["instrument_type"], pair[0]["source_coin"]))
            wire["catalog"]["records"], wire["eligibility"] = zip(*pairs, strict=True)
            await route.fulfill(response=response, json=wire)

        refresh = main.get_by_role("button", name="Refresh discovery")
        await page.route("**/market-universe", large_catalog)
        await refresh.click()
        await expect(markets.get_by_text("2,006 of 2,006 discovered markets")).to_be_visible()
        await expect(markets.get_by_role("article")).to_have_count(12)
        await markets.get_by_role("button", name="Next").click()
        await expect(markets.get_by_text("Page 2 of 168")).to_be_visible()
        await search.fill("test1999")
        await expect(markets.get_by_role("heading", name="TEST1999", exact=True)).to_be_visible()
        await page.unroute("**/market-universe")
        await markets.get_by_role("button", name="Clear filters").click()
        await refresh.click()
        await expect(markets.get_by_text("6 of 6 discovered markets")).to_be_visible()
        async def stale_catalog(route):
            response = await route.fetch()
            wire = await response.json()
            wire["availability"] = "STALE"
            for record, decision in zip(wire["catalog"]["records"], wire["eligibility"], strict=True):
                record["metadata_status"] = "STALE"
                if record["listed"]:
                    decision["reason"] = "STALE_METADATA"
                decision["discovery_eligible"] = False
            await route.fulfill(response=response, json=wire)

        await page.route("**/market-universe", stale_catalog)
        await refresh.click()
        await expect(markets.get_by_role("button", name="Open Research for xyz:GOLD")).to_be_disabled()
        await expect(markets.get_by_text("Discovery is stale.", exact=False)).to_be_visible()
        await page.unroute("**/market-universe")
        await page.route("**/market-universe", paper.testnet_catalog)
        await refresh.click()
        await expect(markets.get_by_text("TESTNET", exact=True)).to_be_visible()
        await markets.get_by_role("button", name="Details for xyz:GOLD").click()
        await expect(markets.get_by_text("HYPERLIQUID:TESTNET:HIP3_PERP:xyz:GOLD", exact=True)).to_be_visible()
        await markets.get_by_role("button", name="Details for xyz:GOLD").click()
        await page.unroute("**/market-universe")
        await refresh.click()
        await expect(markets.get_by_text("MAINNET", exact=True)).to_be_visible()
        passed("Retained stale metadata disables launch, and network refresh replaces qualified identity")
        await expect(btc.get_by_text("65,012.5", exact=True)).to_be_visible()
        sort = markets.get_by_role("combobox", name="Sort by")
        await sort.select_option("mark_price")
        await capture("market-explorer", ".marketExplorer, .experienceMode")
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.evaluate("""() => window.scrollTo(0,
            document.querySelector('.explorerCards').getBoundingClientRect().top + scrollY - 215)""")
        await page.screenshot(path=args.output / "market-explorer-cards-390.png")
        report["screenshots"].append("market-explorer-cards-390.png")
        await page.set_viewport_size({"width": 1440, "height": 1000})
        await sort.select_option("alphabetical")
        await search.fill("missing")
        await expect(markets.get_by_text("1 of 6 discovered markets")).to_be_visible()
        await expect(markets.locator(".explorerObservation").get_by_text("Unavailable", exact=True)).to_be_visible()
        await capture("market-explorer-missing", ".marketExplorer, .experienceMode")
        await search.fill("")

        summary_url = "**/market-universe/market-summaries"
        fields = ("mark_price", "oracle_price", "previous_day_price", "funding_rate", "day_notional_volume",
                  "open_interest_base", "mark_change_vs_previous_day_percent")
        refresh_observations = main.get_by_role("button", name="Refresh observations")

        def timestamp(value):
            return value.isoformat(timespec="microseconds").replace("+00:00", "Z")

        async def summary_state(route, error=None, stale=False):
            response = await route.fetch()
            wire = await response.json()
            now = datetime.now(timezone.utc)
            for row in wire["results"]:
                if row["status"] != "CURRENT":
                    continue
                if error or stale:
                    row.update({field: None for field in fields})
                    row.update(status="ERROR" if error else "STALE", error=error,
                               observed_at=timestamp(now - timedelta(seconds=30)) if stale else None,
                               valid_until=timestamp(now) if stale else None, observation_fingerprint=None)
                else:
                    row.update(observed_at=timestamp(now), valid_until=timestamp(now + timedelta(seconds=2)))
                    capture = {k: v for k, v in row.items() if k != "observation_fingerprint"}
                    capture["catalog_fingerprint"] = wire["catalog_fingerprint"]
                    row["observation_fingerprint"] = sha256(
                        json.dumps(capture, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            wire["evaluated_at"] = timestamp(now)
            await route.fulfill(response=response, json=wire)

        for error, message in (("TIMEOUT", "Provider timeout"), ("RATE_LIMITED", "Provider rate limit"),
                               (None, "Stale")):
            async def fulfill_status(route):
                await summary_state(route, error, stale=error is None)
            await page.route(summary_url, fulfill_status)
            await refresh_observations.click()
            await expect(btc.get_by_text(message, exact=True)).to_be_visible()
            await expect(btc.get_by_text("65,012.5", exact=True)).to_be_hidden()
            await page.unroute(summary_url, fulfill_status)
        async def expiring(route):
            await summary_state(route)

        await page.route(summary_url, expiring)
        await refresh_observations.click()
        await expect(btc.get_by_text("65,012.5", exact=True)).to_be_visible()
        await expect(btc.get_by_text("Stale", exact=True)).to_be_visible(timeout=5000)
        await expect(btc.get_by_text("65,012.5", exact=True)).to_be_hidden()
        await page.unroute(summary_url, expiring)

        arrived, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def old_namespace(route):
            if route.request.post_data_json["market_keys"] == ["HYPERLIQUID:MAINNET:CORE_PERP::BTC"]:
                arrived.set()
                try:
                    await release.wait()
                    await summary_state(route, "TIMEOUT")
                except Exception as exc:
                    if "canceled" not in str(exc).lower() and "aborted" not in str(exc).lower():
                        raise
                finally:
                    finished.set()
            else:
                await route.continue_()

        await page.route(summary_url, old_namespace)
        await search.fill("btc")
        await asyncio.wait_for(arrived.wait(), 10)
        await search.fill("xyz")
        gold = markets.get_by_role("article").filter(has=page.get_by_role("heading", name="xyz:GOLD", exact=True))
        await expect(gold.get_by_text("2,405.25", exact=True)).to_be_visible()
        release.set()
        await asyncio.wait_for(finished.wait(), 10)
        await expect(gold.get_by_text("2,405.25", exact=True)).to_be_visible()
        await expect(markets.get_by_text("Provider timeout", exact=True)).to_have_count(0)
        await page.unroute(summary_url, old_namespace)
        await search.fill("")
        passed("Source fields, page sort, missing data, timeout, rate limit, server/client expiry and late DEX request retirement")
        passed("2,006 records remain searchable with 12 cards mounted per page and recover on refresh")

        await mode("Starter").focus()
        await page.keyboard.press("Tab")
        await expect(mode("Pro")).to_be_focused()
        await page.keyboard.press("Space")
        await expect(mode("Pro")).to_have_attribute("aria-pressed", "true")
        await page.keyboard.press("Shift+Tab")
        await expect(mode("Starter")).to_be_focused()
        await page.keyboard.press("Enter")
        await expect(mode("Starter")).to_have_attribute("aria-pressed", "true")
        await nav.get_by_role("link", name="Home", exact=True).click()
        await expect(main.get_by_role("heading", name="Start with a market")).to_be_visible()
        await main.get_by_role("link", name="Explore markets").click()
        await markets.get_by_role("button", name="Open Research for xyz:GOLD").click()
        guided = main.get_by_role("region", name="Guided PAPER research")
        selector = guided.get_by_role("combobox", name="Discovered perpetual")
        await expect(selector).to_have_value("HYPERLIQUID:MAINNET:HIP3_PERP:xyz:GOLD")
        await expect(guided.get_by_role("heading", name="Step 4 · Review results")).to_be_visible()
        await expect(guided.get_by_text("2,405.25 provider quote / base", exact=True)).to_be_visible()
        await expect(guided.get_by_role("textbox", name="Synthetic reference price")).to_have_value("")
        await expect(guided.get_by_role("combobox", name="PAPER research mode")).to_be_hidden()
        check = guided.get_by_role("button", name="Check PAPER eligibility")
        run_button = guided.get_by_role("button", name="Run local PAPER")
        reference = guided.get_by_role("textbox", name="Synthetic reference price")
        await selector.select_option("HYPERLIQUID:MAINNET:CORE_PERP::OLD")
        await reference.fill("2500")
        await check.click()
        await expect(guided.get_by_text("MARKET_DELISTED", exact=True)).to_be_visible()
        await expect(run_button).to_be_disabled()
        await selector.select_option("HYPERLIQUID:MAINNET:HIP3_PERP:xyz:GOLD")
        await guided.get_by_role("combobox", name="PAPER scenario").select_option("HIGH_VOLATILITY")
        await expect(guided.get_by_text("Alternating large price moves.", exact=False)).to_be_visible()
        await capture("starter", ".guidedPaper, .experienceMode")
        async with page.expect_request("**/generalized-paper/eligibility") as pending:
            await check.click()
        payload = (await pending.value).post_data_json
        assert payload["identity"]["dex"] == "xyz" and payload["scenario"] == "HIGH_VOLATILITY"
        await expect(run_button).to_be_enabled()

        arrived, release = asyncio.Event(), asyncio.Event()

        async def delay_result(route):
            response = await route.fetch()
            arrived.set()
            await release.wait()
            await route.fulfill(response=response)

        await page.route("**/generalized-paper/run", delay_result)
        await run_button.evaluate("e => {e.click(); e.click(); e.click()}")
        await asyncio.wait_for(arrived.wait(), 20)
        await choose_mode("Pro")
        pro = main.get_by_role("region", name="Generalized PAPER research")
        await expect(pro.get_by_text("Running local PAPER simulation…")).to_be_visible()
        await expect(pro.get_by_role("button", name="Run local PAPER")).to_be_disabled()
        await choose_mode("Institutional")
        await choose_mode("Starter")
        release.set()
        result = main.get_by_role("region", name="PAPER result evidence")
        await expect(result.get_by_role("status")).to_contain_text("xyz:GOLD")
        for label in ("Net P&L", "Fees in hypothetical", "Funding in hypothetical", "Inventory in base", "Simulated Risk Firewall status"):
            await expect(result.get_by_text(label, exact=False)).to_be_visible()
        await expect(result.get_by_text("Actual returns are unknown.", exact=False)).to_be_visible()
        await expect(guided.get_by_role("heading", name="Market Eligibility")).to_be_visible()
        quote = guided.get_by_role("region", name="Quote Economics")
        await quote.get_by_role("button", name="Load PAPER quote cohorts").click()
        await expect(quote.get_by_role("combobox", name="Simulated quote cohort")).to_be_visible()
        await nav.get_by_role("link", name="Results", exact=True).click()
        await expect(main.get_by_role("heading", name="PAPER results", exact=True)).to_be_focused()
        await expect(result).to_be_visible()
        assert sum(url.endswith("/generalized-paper/run") for url in writes) == 1
        passed("Starter eligibility, rejection and genuine worker outcome, with one run across three mode changes and Results")

        await choose_mode("Pro")
        await expect(result).to_be_visible()
        await expect(pro.get_by_role("combobox", name="PAPER research mode")).to_be_visible()
        await expect(pro.get_by_role("combobox", name="PAPER research mode").locator("option", has_text="Asset-aware PAPER")).to_have_count(1)
        await expect(pro.get_by_role("heading", name="Funding/Basis")).to_be_visible()
        await capture("simulation-advanced", ".experienceMode, #page-content")
        await nav.get_by_role("link", name="Supervisory Agents", exact=True).click()
        await expect(main.get_by_role("heading", name="Agent intelligence workspace")).to_be_visible()
        await page.screenshot(path=args.output / "agents-1440.png")
        report["screenshots"].append("agents-1440.png")
        await main.get_by_role("link", name="Open research advisory agents").click()
        await expect(result).to_be_visible()
        await nav.get_by_role("link", name="Historical Replay", exact=True).click()
        await expect(main.get_by_role("heading", name="Historical Replay Studio", exact=True)).to_be_visible()
        await nav.get_by_role("link", name="Market vs Research", exact=True).click()
        await expect(main.get_by_role("button", name="Market vs Research", exact=True)).to_have_attribute("aria-pressed", "true")
        await nav.get_by_role("link", name="AMM Settings", exact=True).click()
        await expect(main.get_by_role("heading", name="AMM Settings", exact=True)).to_be_visible()
        await capture("pro-amm", ".experienceMode, #page-content")
        model = main.get_by_role("combobox", name="AMM Model")
        await expect(model.locator("option")).to_have_count(2)
        assert [text.strip() for text in await model.locator("option").all_text_contents()] == ["CONSTANT_PRODUCT", "CONCENTRATED"]
        await nav.get_by_role("link", name="Strategy", exact=True).click()
        await expect(main.get_by_role("region", name="Current virtual pool & authorization")).to_be_visible()
        await nav.get_by_role("link", name="Dashboard", exact=True).click()
        overview = main.get_by_role("region", name="Pro research overview")
        await expect(overview.get_by_text("Operational market", exact=True)).to_be_visible()
        await expect(overview.get_by_text("Research market", exact=True)).to_be_visible()
        await expect(overview.get_by_text("2,405.25 provider quote / base", exact=True)).to_be_visible()
        await capture("pro", ".experienceMode, .modeOverview")
        passed("Pro overview and both AMMs, with supervisory, advisory, replay, comparison and asset-aware research")

        await choose_mode("Institutional")
        await nav.get_by_role("link", name="Portfolio Research", exact=True).click()
        portfolio = main.get_by_role("group", name="Portfolio Research Terminal")
        await expect(portfolio.get_by_text("HYPOTHETICAL · PAPER ONLY", exact=False)).to_be_visible()
        sections = portfolio.get_by_role("navigation", name="Portfolio workspace sections")
        await sections.get_by_role("button", name="Stress Lab", exact=True).click()
        await sections.get_by_role("button", name="Provenance", exact=True).click()
        await expect(sections.get_by_role("button", name="Provenance")).to_have_attribute("aria-pressed", "true")
        await sections.get_by_role("button", name="Configure", exact=True).click()
        await expect(portfolio.get_by_role("region", name="Institutional overview")).to_be_visible()
        await capture("institutional", ".experienceMode, .modeOverview")
        for label, path in (("Risk", "risk"), ("Audit logs", "logs"), ("Vault", "vault"),
                            ("Execution evidence", "execution"), ("Analytics", "analytics")):
            await nav.get_by_role("link", name=label, exact=True).click()
            await expect(page).to_have_url(BASE + "/#/" + path)
        await route("settings", "Settings & system configuration")
        await page.reload()
        await expect(mode("Institutional")).to_have_attribute("aria-pressed", "true")
        await expect(page).to_have_url(BASE + "/#/settings")
        await page.go_back()
        await expect(page).to_have_url(BASE + "/#/analytics")
        await page.go_forward()
        await expect(page).to_have_url(BASE + "/#/settings")
        await route("dashboard", "Liquidity terminal")
        passed("Institutional portfolio, stress, provenance, risk, audit and accounting routes, with legacy refresh and history")

        await choose_mode("Starter")
        await route("markets", "Market Explorer")
        await page.set_viewport_size({"width": 390, "height": 844})
        open_nav = page.get_by_role("button", name="Open navigation")
        await open_nav.focus()
        await page.keyboard.press("Enter")
        await expect(page.get_by_role("dialog", name="Terminal navigation")).to_be_visible()
        await page.keyboard.press("Escape")
        await expect(open_nav).to_be_focused()
        await page.set_viewport_size({"width": 1440, "height": 1000})
        passed("Keyboard mode selection and mobile drawer return focus")
        if extension is not None:
            await extension(page, report, choose_mode, capture, passed)
        if engine == "chromium":
            base = await page.evaluate("({width: innerWidth, dpr: devicePixelRatio})")
            settings = await context.new_page()
            await settings.goto("chrome://settings/appearance")
            await settings.get_by_role("combobox", name="Page zoom").select_option("2")
            await settings.close()
            await page.bring_to_front()
            await page.wait_for_function("dpr => devicePixelRatio === dpr * 2", arg=base["dpr"])
            report["zoom_200"] = await page.evaluate("({width: innerWidth, document: document.documentElement.scrollWidth, dpr: devicePixelRatio})")
            assert abs(report["zoom_200"]["width"] * 2 - base["width"]) <= 2, report["zoom_200"]
            assert report["zoom_200"]["document"] <= report["zoom_200"]["width"] + 1, report["zoom_200"]
            await expect(modes).to_be_visible()
            await open_nav.focus()
            await page.keyboard.press("Enter")
            await expect(page.get_by_role("dialog", name="Terminal navigation")).to_be_visible()
            await page.keyboard.press("Escape")
            await expect(open_nav).to_be_focused()
            print("PASS actual Chromium 200% browser zoom", flush=True)
        assert not report["page_errors"], report["page_errors"]
        assert all("/generalized-paper/" in url or url.endswith(RESEARCH_WRITES + extra_writes) for url in writes), writes
        assert not any(row["violations"] for row in report["axe"]), report["axe"]
        await context.close()


def add_arguments(parser):
    parser.add_argument("--python", required=True)
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    parser.add_argument("--axe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)


def run_suite(args, extension=None, *, backend_app="browser-phase182:fixture_app", extra_writes=()):
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"status": "FAIL", "source": "Local DEMO terminal and deterministic discovery and market-context fixtures. PAPER uses the real local worker.",
              "workflows": [], "viewports": [], "screenshots": [], "axe": [], "page_errors": [], "writes": []}
    environment = {**os.environ, "MARKET_DATA_MODE": "DEMO", "EXECUTION_MODE": "PAPER",
                   "ENABLE_HYPERLIQUID_TESTNET_ORDERS": "false", "LIVE_OBSERVATIONS_ENABLED": "false",
                   "LIVE_STREAMS_ENABLED": "false", "REDIS_ENABLED": "false"}
    processes = []
    try:
        with TemporaryDirectory() as scratch, ExitStack() as logs:
            environment["PHASE1641_FIXTURE_ROOT"] = str(Path(scratch) / "replay")
            try:
                for directory, command in (
                    ("backend", [args.python, "-m", "uvicorn", backend_app, "--factory",
                                 "--app-dir", str(ROOT / "frontend/tests"), "--host", "127.0.0.1", "--port", "8000"]),
                    ("frontend", ["node", "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--strictPort"]),
                ):
                    log = logs.enter_context((args.output / f"{directory}.log").open("w"))
                    processes.append(subprocess.Popen(command, cwd=ROOT / directory,
                                                       env=environment, stdout=log, stderr=subprocess.STDOUT))
                asyncio.run(run(args, str(Path(scratch) / "browser"), report, extension, extra_writes))
                report["status"] = "PASS"
            finally:
                for process in reversed(processes):
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
    finally:
        (args.output / "browser-results.json").write_text(json.dumps(report, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    add_arguments(parser)
    run_suite(parser.parse_args())


if __name__ == "__main__":
    main()
