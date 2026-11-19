"""Chromium against the real API and worker with read-only metadata fixtures."""
import argparse
import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def fixture_app():
    from app.main import app
    from app.agents.advisory_coordinator import AdvisoryCoordinator
    from app.market_data.advisory_market_observations import _epoch_ms
    from app.market_data.market_universe_discovery import DiscoveryFailure
    from app.market_data.models import utcnow
    from app.market_data.market_universe_discovery import MarketUniverseDiscovery

    def provider(method, dex, deadline):
        if method == "perpDexs":
            return [None, {"name": "xyz"}, {"name": "missing"}]
        if method == "spotMeta":
            return {"tokens": [{"index": 0, "name": "USDC", "isCanonical": True,
                                "tokenId": "0x6d1e7cde53ba9467b783cb7c530ce054"},
                               {"index": 1, "name": "USDC", "tokenId": "0x00000000000000000000000000000001"}]}
        def row(name, size, mode="strictIsolated"):
            return {"name": name, "szDecimals": size, "marginMode": mode, "marginTableId": 10, "maxLeverage": 10}
        if dex == "missing":
            return {"universe": [row("missing:GOLD", 3)]}
        if dex == "xyz":
            return {"universe": [row("xyz:GOLD", 3, "noCross"), row("xyz:UNKNOWN", 3, "unsupported")], "collateralToken": 1}
        return {"universe": [row("DOGE", 2), row("BTC", 3),
                             {"name": "OLD", "szDecimals": 2, "isDelisted": True}], "collateralToken": 0}

    def public(operation, identity, deadline, **_kwargs):
        coin = identity.exchange_coin
        if coin == "missing:GOLD":
            raise DiscoveryFailure("RATE_LIMITED")
        at = _epoch_ms(utcnow())
        if operation == "metaAndAssetCtxs":
            metadata = provider("meta", identity.dex, deadline)
            return [metadata, [{"coin": row["name"], "markPx": "100.13", "oraclePx": None if coin == "xyz:UNKNOWN" else "100",
                                "funding": "0.0002", "openInterest": "100"} for row in metadata["universe"]]]
        if operation == "l2Book":
            return {"coin": coin, "time": at - (11_000 if coin == "xyz:GOLD" else 20),
                    "levels": [[{"px": "100.10", "sz": "1"}], [{"px": "100.14", "sz": "1"}]]}
        assert operation == "fundingHistory"
        return [{"coin": coin, "time": at - 200, "fundingRate": "-0.0002"}]

    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(instance):
        async with original(instance):
            previous = instance.state.market_universe_discovery
            discovery = MarketUniverseDiscovery(enabled=True, network="MAINNET", client=provider)
            previous_advisory = instance.state.advisory_coordinator
            advisory = AdvisoryCoordinator(discovery)
            advisory._observations._client.request = public
            instance.state.market_universe_discovery = discovery
            instance.state.advisory_coordinator = advisory
            try:
                yield
            finally:
                instance.state.market_universe_discovery = previous
                instance.state.advisory_coordinator = previous_advisory
                await advisory.close()
                await discovery.close()

    app.router.lifespan_context = lifespan
    return app


async def browser_check(chromium):
    from playwright.async_api import async_playwright, expect

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=chromium, args=["--no-sandbox"])
        try:
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            page_errors, writes = [], []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on("request", lambda request: writes.append(request.url)
                    if request.method in {"POST", "PUT", "PATCH", "DELETE"} else None)
            async with asyncio.timeout(20):
                while True:
                    try:
                        if (await page.request.get("http://127.0.0.1:5173/api/v1/health", timeout=1000)).ok:
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(0.15)
            await page.goto("http://127.0.0.1:5173/#/simulation")
            tabs = page.get_by_role("navigation", name="Simulation research workspaces")
            native_market = page.get_by_role("combobox", name="Research Perpetual Market")
            await expect(native_market.locator("option")).to_have_count(3)
            for market in ("BTC", "ETH", "SOL"):
                await native_market.select_option(market)
            await tabs.get_by_role("button", name="Generalized PAPER").click()
            market = page.get_by_role("combobox", name="Discovered perpetual")
            price = page.get_by_role("textbox", name="Synthetic reference price")
            scenario = page.get_by_role("combobox", name="PAPER scenario")
            check = page.get_by_role("button", name="Check PAPER eligibility")
            run = page.get_by_role("button", name="Run local PAPER")
            panel = page.get_by_role("region", name="Generalized PAPER research")
            result = panel.get_by_role("region", name="PAPER result evidence")
            refresh = panel.get_by_role("button", name="Refresh discovery")
            await expect(page.get_by_text("Venue fees, funding", exact=False)).to_be_visible()
            await expect(run).to_be_disabled()
            await market.select_option("HYPERLIQUID:MAINNET:CORE_PERP::OLD")
            await price.fill("0.1234")
            await check.click()
            await expect(page.get_by_text("MARKET_DELISTED", exact=True)).to_be_visible()
            await expect(run).to_be_disabled()
            print("PASS delisting renders a typed rejection and disables run", flush=True)
            for key, reference, coin in (
                ("HYPERLIQUID:MAINNET:CORE_PERP::DOGE", "0.1234", "DOGE"),
                ("HYPERLIQUID:MAINNET:HIP3_PERP:xyz:GOLD", "2500", "xyz:GOLD"),
            ):
                await market.select_option(key)
                await price.fill(reference)
                await scenario.select_option("FLASH_MOVE")
                await expect(run).to_be_disabled()
                await check.click()
                await expect(run).to_be_enabled()
                await run.click()
                await expect(result.get_by_role("status")).to_contain_text(f"Simulated PAPER result for {coin}")
                await expect(result.get_by_text("Net P&L in hypothetical quote units")).to_be_visible()
                await expect(result.get_by_text("Synthetic top depth", exact=False)).to_be_visible()
                await expect(result.get_by_text("Modeled maker fee 0 bps", exact=False)).to_be_visible()
                await expect(result.get_by_text("Hypothetical funding disabled.", exact=False)).to_be_visible()
                await expect(result.get_by_text("Exchange collateral, margin, liquidation", exact=False)).to_be_visible()
                await expect(panel.get_by_text(key, exact=True)).to_be_visible()
                print(f"PASS {coin} completes through the real worker with synthetic labeling", flush=True)
            await page.set_viewport_size({"width": 390, "height": 844})
            provenance = result.get_by_text("Result fingerprint and provenance", exact=True)
            await provenance.focus()
            await page.keyboard.press("Enter")
            await expect(result.get_by_text("Reference confidence and timestamps", exact=False)).to_be_visible()
            assert await result.evaluate("(node) => node.scrollWidth <= node.clientWidth")
            assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not await panel.get_by_role("button", name=re.compile(r"Trade|Submit order|Execute live", re.I)).count()
            print("PASS narrow financial evidence and keyboard-accessible provenance", flush=True)

            await market.select_option("HYPERLIQUID:MAINNET:CORE_PERP::DOGE")
            await expect(result).to_have_count(0)
            await expect(run).to_be_disabled()
            await market.select_option("HYPERLIQUID:MAINNET:HIP3_PERP:xyz:GOLD")
            await panel.get_by_role("checkbox", name="Apply hypothetical funding", exact=False).check()
            await check.click()
            await expect(run).to_be_enabled()
            await run.click()
            await expect(result.get_by_text("Hypothetical funding interval 1 s.", exact=False)).to_be_visible()

            checking = asyncio.Event()
            release = asyncio.Event()
            async def unavailable(route):
                checking.set()
                await release.wait()
                await route.fulfill(status=429, body="busy")
            await page.route("**/generalized-paper/run", unavailable)
            try:
                await run.click()
                await asyncio.wait_for(checking.wait(), 5)
                await expect(panel.get_by_text("Running local PAPER simulation…")).to_have_attribute("role", "status")
                await expect(result).to_have_count(0)
            finally:
                release.set()
            await expect(panel.get_by_role("alert")).to_contain_text("PAPER worker is busy")
            await expect(run).to_be_disabled()
            await page.unroute("**/generalized-paper/run")
            print("PASS proposal and market edits, accessible run status and failed-result retirement", flush=True)

            await check.click()
            await expect(run).to_be_enabled()
            await run.click()
            await expect(result).to_be_visible()
            await refresh.click()
            await expect(result).to_have_count(0)
            await expect(run).to_be_disabled()
            await expect(check).to_be_enabled()

            async def testnet_catalog(route):
                response = await route.fetch()
                wire = await response.json()
                wire["network"] = "TESTNET"
                wire["catalog_fingerprint"] = "9" * 64
                for row in (*wire["catalog"]["records"], *wire["eligibility"]):
                    row["identity"]["network"] = "TESTNET"
                await route.fulfill(response=response, json=wire)

            await check.click()
            await expect(run).to_be_enabled()
            await run.click()
            await expect(result).to_be_visible()
            advisory = panel.get_by_role("region", name="Market Eligibility")
            await advisory.get_by_role("button", name="Evaluate market eligibility").click()
            await expect(advisory.get_by_text("Discovery suitability")).to_be_visible()
            await page.route("**/market-universe", testnet_catalog)
            await page.evaluate("window.dispatchEvent(new Event('visibilitychange'))")
            await expect(panel.get_by_text("TESTNET metadata available.", exact=False)).to_be_visible()
            await expect(advisory).to_have_count(0)
            await expect(market).to_have_value("")
            await expect(result).to_have_count(0)
            await expect(run).to_be_disabled()
            await page.unroute("**/market-universe")
            await refresh.click()
            await expect(panel.get_by_text("MAINNET metadata available.", exact=False)).to_be_visible()
            await market.select_option("HYPERLIQUID:MAINNET:HIP3_PERP:xyz:GOLD")
            print("PASS explicit refresh and automatic network replacement retire admission and advisory evidence", flush=True)

            await check.click()
            await expect(run).to_be_enabled()
            await run.click()
            await expect(result).to_be_visible()
            await page.route("**/market-universe",
                lambda route: route.fulfill(status=500, json={"detail": "fixture refresh failure"}))
            await page.evaluate("window.dispatchEvent(new Event('visibilitychange'))")
            await expect(panel.get_by_role("alert")).to_have_text("Discovery could not be loaded.")
            await expect(result).to_have_count(0)
            await expect(run).to_be_disabled()
            await page.unroute("**/market-universe")
            await refresh.click()
            await expect(check).to_be_enabled()
            print("PASS failed background refresh clears evidence and announces failure", flush=True)

            await price.fill("2500.123")
            await expect(run).to_be_disabled()
            await check.click()
            await expect(page.get_by_text("PRICE_UNREPRESENTABLE", exact=True)).to_be_visible()
            await expect(run).to_be_disabled()
            print("PASS edits retire admission and invalid precision renders a typed rejection", flush=True)
            await page.clock.install()
            await price.fill("2500")
            await check.click()
            await expect(run).to_be_enabled()
            await page.clock.fast_forward(61_000)
            await expect(page.get_by_text("PAPER eligibility expired.", exact=False)).to_be_visible()
            await expect(run).to_be_disabled()
            print("PASS expiry retires eligible action in the browser", flush=True)
            await tabs.get_by_role("button", name="Scenario & optimization").click()
            await expect(native_market).to_have_value("SOL")
            assert not page_errors, page_errors
            assert writes and all("/api/v1/generalized-paper/" in url or url.endswith("/market-universe/advisory")
                                  for url in writes), writes
            print("PASS native selection preserved and write requests confined to PAPER", flush=True)
        finally:
            await browser.close()


async def browser_risk_check(chromium):
    """Use the same real API and worker with fixture-only public metadata."""
    from playwright.async_api import Error, async_playwright, expect

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=chromium, args=["--no-sandbox"])
        try:
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            errors, writes = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: writes.append(request.url)
                    if request.method in {"POST", "PUT", "PATCH", "DELETE"} else None)
            await page.goto("http://127.0.0.1:5173/#/simulation")
            await page.get_by_role("button", name="Generalized PAPER").click()
            panel = page.get_by_role("region", name="Generalized PAPER research")
            sources = panel.get_by_role("region", name="Public collateral and margin evidence")
            market = panel.get_by_role("combobox", name="Discovered perpetual")
            mode = panel.get_by_role("combobox", name="Risk mode", exact=True)
            margin_mode = panel.get_by_role("combobox", name="Research margin mode")
            price = panel.get_by_role("textbox", name="Synthetic reference price")
            scenario = panel.get_by_role("combobox", name="PAPER scenario")
            capital = panel.get_by_role("textbox", name="Research capital", exact=False)
            check = panel.get_by_role("button", name="Check PAPER eligibility")
            run = panel.get_by_role("button", name="Run local PAPER")
            result = panel.get_by_role("region", name="Modeled research risk")
            source_option = mode.locator('option[value="SOURCE_CONSTRAINED"]')
            core = "HYPERLIQUID:MAINNET:CORE_PERP::BTC"
            hip = "HYPERLIQUID:MAINNET:HIP3_PERP:xyz:GOLD"
            await expect(mode).to_have_value("OFF")
            await market.select_option(core)
            await expect(source_option).to_have_js_property("disabled", False)
            await expect(sources.get_by_text("Observed margin tiers")).to_be_visible()
            await expect(sources.get_by_text("Strict isolated", exact=True)).to_be_visible()
            await price.fill("100")
            await mode.select_option("HYPOTHETICAL")
            await expect(check).to_be_disabled()
            await expect(panel.get_by_role("status").filter(has_text="Research capital must")).to_be_visible()
            await capital.fill("10000")
            await panel.get_by_role("textbox", name="Initial margin fraction").fill("0.2")
            await panel.get_by_role("textbox", name="Maintenance margin fraction").fill("0.1")
            await panel.get_by_role("button", name="Add stress scenario").click()
            await panel.get_by_role("textbox", name="Stress name").fill("decline")
            await panel.get_by_role("textbox", name="Price shock (bps)").fill("-2000")
            await panel.get_by_role("textbox", name="Collateral haircut (bps)").fill("300")
            await panel.get_by_role("textbox", name="Capital reduction (bps)").fill("50")
            await panel.get_by_role("textbox", name="Funding cost surcharge (bps)").fill("15")
            await panel.get_by_role("textbox", name="Fee surcharge (bps)").fill("10")
            await check.click()
            await expect(run).to_be_enabled()
            await run.click()
            await expect(result.get_by_text("Modeled margin and headroom")).to_be_visible()
            await expect(result.get_by_role("region", name="Modeled stress results").get_by_text("decline", exact=False)).to_be_visible()
            await expect(result.get_by_text("Adverse modeled P&L")).to_be_visible()
            await expect(result.get_by_text("PAPER quote units", exact=True)).to_be_visible()
            print("PASS Core hypothetical risk and bounded stress settings/results", flush=True)

            await market.select_option(hip)
            await expect(result).to_have_count(0)
            await expect(run).to_be_disabled()
            await expect(sources.get_by_text("0x00000000000000000000000000000001", exact=False)).to_be_visible()
            await check.click()
            await expect(run).to_be_enabled()
            await run.click()
            await expect(result.get_by_text("Hypothetical risk research", exact=False)).to_be_visible()
            print("PASS HIP-3 hypothetical risk and same-symbol collateral separation", flush=True)

            await mode.select_option("SOURCE_CONSTRAINED")
            await margin_mode.select_option("NO_CROSS")
            await panel.get_by_role("textbox", name="Research leverage (whole number)").fill("5")
            rate = panel.get_by_role("textbox", name="Hypothetical valuation", exact=False)
            await expect(check).to_be_disabled()
            await rate.fill("1.5")
            await check.click()
            await expect(run).to_be_enabled()
            await rate.fill("1.75")
            await expect(run).to_be_disabled()
            await check.click()
            await expect(run).to_be_enabled()
            await run.click()
            await expect(result.get_by_text("DOCUMENTED_HYPERLIQUID_TIERS", exact=False)).to_be_visible()
            await expect(result.get_by_text("1.75 USDC per PAPER quote unit")).to_be_visible()
            await expect(result.get_by_text("Account balances, shared-capital netting", exact=False)).to_be_visible()
            print("PASS source-constrained HIP-3 and changed valuation invalidation", flush=True)

            await page.set_viewport_size({"width": 390, "height": 844})
            summary = result.get_by_text("Per-frame Risk Firewall decisions", exact=True)
            await summary.focus()
            await page.keyboard.press("Enter")
            await expect(result.get_by_text("Frame 1 ·", exact=False).first).to_be_visible()
            assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert await panel.evaluate("(node) => node.scrollWidth <= node.clientWidth")
            accessible = await result.aria_snapshot()
            assert "heading \"Modeled margin and headroom\"" in accessible
            assert "USDC" in accessible and "basis points" in accessible and "Frame 1" in accessible
            print("PASS narrow results, keyboard navigation and Chromium accessible names and units", flush=True)

            await market.select_option("HYPERLIQUID:MAINNET:HIP3_PERP:missing:GOLD")
            await expect(sources.get_by_text("omits a collateral token", exact=False)).to_be_visible()
            await expect(source_option).to_have_js_property("disabled", True)
            await expect(check).to_be_disabled()
            await market.select_option("HYPERLIQUID:MAINNET:HIP3_PERP:xyz:UNKNOWN")
            await expect(sources.get_by_text("reports an unsupported margin mode", exact=False)).to_be_visible()
            await expect(source_option).to_have_js_property("disabled", True)
            print("PASS missing collateral and unsupported policy explain disabled source mode", flush=True)

            await market.select_option(core)
            await mode.select_option("HYPOTHETICAL")
            await panel.get_by_role("button", name="Remove stress 1").click()
            await panel.get_by_role("textbox", name="Initial margin fraction").fill("1")
            await panel.get_by_role("textbox", name="Maintenance margin fraction").fill("1")
            for budget, name, assertion in (
                ("300", "QUIET", r"retirement occurred in [1-9][0-9]* of 40 frames"),
                ("700", "HIGH_VOLATILITY", r"Recorded states [^.]*HALT"),
            ):
                await capital.fill(budget)
                await scenario.select_option(name)
                await check.click()
                await expect(run).to_be_enabled()
                await run.click()
                await expect(result.get_by_text(re.compile(assertion))).to_be_visible()
            await result.get_by_text("Per-frame Risk Firewall decisions").click()
            await expect(result.get_by_text("PAPER modeled maintenance headroom exhausted", exact=False).first).to_be_visible()
            halted = await result.get_by_text(re.compile(r"^Frame \d+ · HALT$")).first.inner_text()
            quote = panel.get_by_role("region", name="Quote Economics")
            await quote.get_by_role("button", name="Load PAPER quote cohorts").click()
            await quote.get_by_role("combobox", name="Simulated quote cohort").select_option(halted.split()[1])
            await quote.get_by_role("textbox", name="Holding period in seconds").fill("6")
            await quote.get_by_role("textbox", name="Exit slippage in bps").fill("0")
            await quote.get_by_role("textbox", name="Inventory cost in bps").fill("0")
            await quote.get_by_role("button", name="Evaluate quote economics").click()
            await expect(quote.get_by_text("Risk Firewall HALT", exact=False).first).to_be_visible()
            await expect(quote.get_by_role("status")).to_contain_text("unsupported")
            await expect(quote.get_by_role("table")).to_have_count(0)
            print("PASS real worker quote retirement and modeled maintenance HALT reflected in the advisory", flush=True)

            waiting, release = asyncio.Event(), asyncio.Event()
            async def delayed_admission(route):
                response = await route.fetch()
                waiting.set()
                await release.wait()
                try:
                    await route.fulfill(response=response)
                except Error:
                    pass  # The old request has already lost its owner.

            await page.route("**/generalized-paper/eligibility", delayed_admission)
            await check.click()
            try:
                await asyncio.wait_for(waiting.wait(), 10)
                await capital.fill("5000")
                await expect(result).to_have_count(0)
            finally:
                release.set()
            await expect(run).to_be_disabled()
            await page.unroute("**/generalized-paper/eligibility")
            await check.click()
            await expect(run).to_be_enabled()
            await run.click()
            await expect(result.get_by_text("5000 PAPER quote units", exact=True)).to_be_visible()
            print("PASS capital edits invalidate admission and late eligibility cannot overwrite current inputs", flush=True)

            financial_waiting, financial_release = asyncio.Event(), asyncio.Event()
            async def delayed_source(route):
                if "dex=xyz" not in route.request.url:
                    await route.continue_()
                    return
                response = await route.fetch()
                financial_waiting.set()
                await financial_release.wait()
                try:
                    await route.fulfill(response=response)
                except Error:
                    pass

            await page.route("**/market-universe/risk-evidence**", delayed_source)
            await market.select_option(hip)
            try:
                await asyncio.wait_for(financial_waiting.wait(), 10)
                await market.select_option(core)
            finally:
                financial_release.set()
            await expect(sources.get_by_text("Strict isolated", exact=True)).to_be_visible()
            await expect(sources.get_by_text("0x00000000000000000000000000000001", exact=False)).to_have_count(0)
            await page.unroute("**/market-universe/risk-evidence**")
            print("PASS late HIP-3 observation cannot populate the Core selection", flush=True)

            await check.click()
            await expect(run).to_be_enabled()
            await run.click()
            await expect(result).to_be_visible()
            await page.clock.install()
            await page.clock.fast_forward(61_000)
            await expect(run).to_be_disabled()
            await expect(result).to_have_count(0)
            await expect(source_option).to_have_js_property("disabled", True)
            await expect(sources.get_by_text("Financial evidence is stale.", exact=False)).to_be_visible()
            assert not await panel.get_by_role("button", name=re.compile(r"Trade|Submit order|Execute live", re.I)).count()
            assert not errors, errors
            assert writes and all("/api/v1/generalized-paper/" in url or url.endswith("/market-universe/advisory")
                                  for url in writes), writes
            print("PASS provider and admission expiry retire risk actions and completed output, with PAPER-only writes", flush=True)
        finally:
            await browser.close()



async def browser_advisory_check(chromium, axe):
    from playwright.async_api import Error, async_playwright, expect

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=chromium, args=["--no-sandbox"])
        try:
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            errors, writes = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: writes.append(request.url) if request.method == "POST" else None)
            async with asyncio.timeout(20):
                while True:
                    try:
                        if (await page.request.get("http://127.0.0.1:5173/api/v1/health", timeout=1000)).ok:
                            break
                    except Error:
                        pass
                    await asyncio.sleep(0.15)
            await page.goto("http://127.0.0.1:5173/#/simulation")
            await page.get_by_role("button", name="Generalized PAPER", exact=True).click()
            panel = page.get_by_role("region", name="Generalized PAPER research")
            market = panel.get_by_role("combobox", name="Discovered perpetual")
            core = "HYPERLIQUID:MAINNET:CORE_PERP::BTC"
            hip = "HYPERLIQUID:MAINNET:HIP3_PERP:xyz:GOLD"
            await market.select_option(core)
            eligibility = panel.get_by_role("region", name="Market Eligibility")
            operation = eligibility.get_by_role("combobox", name="Advisory research operation")
            evaluate = eligibility.get_by_role("button", name="Evaluate market eligibility")
            await evaluate.focus()
            await page.keyboard.press("Enter")
            await expect(eligibility.get_by_text("Discovery suitability")).to_be_visible()
            await expect(eligibility.get_by_role("status")).to_contain_text("ready")
            await operation.select_option("STANDARD_PAPER")
            await evaluate.click()
            await expect(eligibility.get_by_text("Missing requirements")).to_contain_text("paper proposal")
            print("PASS advisory Core discovery, keyboard action and missing PAPER prerequisites", flush=True)

            observed = panel.get_by_role("region", name="Observed public funding and basis")
            inspect = observed.get_by_role("button", name="Inspect observed funding")
            await inspect.click()
            await expect(observed.get_by_role("cell", name="100.12 venue quote per base")).to_be_visible()
            await observed.get_by_text("Source provenance and freshness").click()
            await expect(observed.get_by_text("Provider event time unavailable.").first).to_be_visible()
            await expect(observed.get_by_text(re.compile(r"^Provider event [0-9]{4}-")).first).to_be_visible()
            await market.select_option(hip)
            await expect(observed.get_by_role("table")).to_have_count(0)
            await inspect.click()
            await expect(observed.get_by_role("table")).to_be_visible()
            await expect(observed.get_by_role("row").filter(has_text="Order-book midpoint")).to_contain_text("Unavailable")
            await market.select_option("HYPERLIQUID:MAINNET:HIP3_PERP:xyz:UNKNOWN")
            await inspect.click()
            await expect(observed.get_by_role("row").filter(has_text="Oracle price")).to_contain_text("Unavailable")
            await expect(observed.get_by_role("row").filter(has_text="Mark price")).to_contain_text("100.13")
            await market.select_option(hip)
            print("PASS advisory Core and HIP-3 fixtures, receipt/event clocks, stale book and missing oracle", flush=True)

            waiting, release = asyncio.Event(), asyncio.Event()
            async def delay(route):
                response = await route.fetch()
                waiting.set()
                await release.wait()
                try:
                    await route.fulfill(response=response)
                except Error:
                    pass

            await page.route("**/market-universe/advisory", delay)
            await inspect.click()
            try:
                await asyncio.wait_for(waiting.wait(), 10)
                await market.select_option("HYPERLIQUID:MAINNET:HIP3_PERP:missing:GOLD")
            finally:
                release.set()
            await expect(observed.get_by_role("table")).to_have_count(0)
            await page.unroute("**/market-universe/advisory", delay)
            await inspect.click()
            await expect(observed.get_by_text("public provider is rate limited", exact=False)).to_be_visible()
            await expect(observed.get_by_role("status")).to_contain_text("Confidence 0%")
            print("PASS advisory DEX change retires delayed data and reports provider backoff", flush=True)

            await market.select_option(hip)
            await panel.get_by_role("textbox", name="Synthetic reference price").fill("3000")
            await panel.get_by_role("combobox", name="PAPER scenario").select_option("HIGH_VOLATILITY")
            await panel.get_by_role("checkbox", name="Apply hypothetical funding", exact=False).check()
            await panel.get_by_role("button", name="Check PAPER eligibility").click()
            run = panel.get_by_role("button", name="Run local PAPER")
            await expect(run).to_be_enabled()
            await run.click()
            await expect(panel.get_by_role("region", name="PAPER result evidence")).to_be_visible(timeout=12_000)
            synthetic = panel.get_by_role("region", name="Synthetic PAPER funding and basis")
            await synthetic.get_by_role("button", name="Inspect synthetic funding").click()
            await expect(synthetic.get_by_role("status")).to_contain_text("scenario synthetic")
            await expect(synthetic.get_by_role("row").filter(has_text="Funding interval")).to_contain_text("1 s")
            print("PASS advisory real PAPER receipt and separate synthetic funding evidence", flush=True)

            quote = panel.get_by_role("region", name="Quote Economics")
            await quote.get_by_role("button", name="Load PAPER quote cohorts").click()
            cohort = quote.get_by_role("combobox", name="Simulated quote cohort")
            await expect(cohort).to_be_visible()
            await quote.get_by_role("textbox", name="Holding period in seconds").fill("6")
            await quote.get_by_role("textbox", name="Exit slippage in bps").fill("0")
            await quote.get_by_role("textbox", name="Inventory cost in bps").fill("0")
            button = quote.get_by_role("button", name="Evaluate quote economics")
            ready, missing = None, False
            for index in (40, 39, 38, 37, 36, 35, 1, 2, 3, 4, 5):
                await cohort.select_option(str(index))
                await button.click()
                status = quote.get_by_role("status").filter(has_text=re.compile(r"^Status "))
                await expect(status).to_be_visible()
                if await quote.get_by_text("matured synthetic markout", exact=False).count():
                    missing = True
                if "Status ready" in await status.inner_text():
                    ready = index
                    await expect(quote.get_by_role("row").filter(has_text="Hypothetical modeled residual edge")).to_be_visible()
                    if missing:
                        break
            assert missing and ready is not None
            if (await cohort.input_value()) != str(ready):
                await cohort.select_option(str(ready))
                await button.click()
                await expect(quote.get_by_role("table")).to_be_visible()
            await expect(quote.get_by_text("modeled negative · Hypothetical PAPER model")).to_be_visible()
            await cohort.select_option("3")
            await quote.get_by_role("textbox", name="Holding period in seconds").fill("10000")
            await button.click()
            await expect(quote.get_by_text("modeled positive · Hypothetical PAPER model")).to_be_visible()
            await expect(quote.get_by_role("row").filter(has_text="Funding carry cost")).to_contain_text("-500.01000020")
            print("PASS advisory real mature cohort reconciles positive and negative modeled edge with configured carry", flush=True)

            await page.set_viewport_size({"width": 390, "height": 844})
            summary = quote.get_by_text("Source provenance and freshness", exact=True)
            await summary.focus()
            await page.keyboard.press("Enter")
            await expect(quote.get_by_text("Snapshot fingerprint", exact=False)).to_be_visible()
            tree = await quote.aria_snapshot()
            assert "table" in tree and "rowheader" in tree and "Matured markout count" in tree
            assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert await quote.evaluate("(node) => node.scrollWidth <= node.clientWidth")
            await quote.get_by_role("button", name="Load PAPER quote cohorts").focus()
            for role, accessible_name in (
                ("combobox", "Simulated quote cohort"), ("textbox", "Holding period in seconds"),
                ("combobox", "Residual exit liquidity"), ("textbox", "Exit slippage in bps"),
                ("textbox", "Inventory cost in bps"), ("button", "Evaluate quote economics"),
            ):
                await page.keyboard.press("Tab")
                await expect(quote.get_by_role(role, name=accessible_name, exact=True)).to_be_focused()
            if axe:
                await page.add_script_tag(path=axe)
                audits = await page.evaluate("""async () => {
                    const result = await axe.run('.paperAdvisory', {runOnly: {type: 'tag',
                        values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']}});
                    return {version: result.testEngine.version, violations: result.violations.map(item => item.id),
                        manual: result.incomplete.map(item => item.id)};
                }""")
                assert not audits["violations"], audits
                print(f"PASS advisory axe {audits['version']} WCAG A/AA scan, manual items {audits['manual']}", flush=True)
            await page.clock.install()
            await page.clock.fast_forward(61_000)
            await expect(quote.get_by_role("table")).to_have_count(0)
            await expect(quote.get_by_text("Advisory evidence expired", exact=False).first).to_be_visible()
            assert not await panel.get_by_role("button", name=re.compile(r"Trade|Submit order|Execute live|Sign wallet", re.I)).count()
            assert not errors, errors
            assert writes and all(re.search(r"/(generalized-paper/(eligibility|run)|market-universe/advisory)$", url) for url in writes)
            print("PASS advisory matured and missing markouts, modeled edge, mobile table, keyboard and expiry", flush=True)
        finally:
            await browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True)
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--advisory-only", action="store_true")
    parser.add_argument("--axe", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "MARKET_DATA_MODE": "DEMO", "EXECUTION_MODE": "PAPER",
           "ENABLE_HYPERLIQUID_TESTNET_ORDERS": "false", "LIVE_OBSERVATIONS_ENABLED": "false",
           "LIVE_STREAMS_ENABLED": "false", "REDIS_ENABLED": "false"}
    commands = (
        (ROOT / "backend", [args.python, "-m", "uvicorn", "browser-phase182:fixture_app", "--factory",
                           "--app-dir", str(ROOT / "frontend/tests"), "--host", "127.0.0.1", "--port", "8000"]),
        (ROOT / "frontend", ["node", "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--strictPort"]),
    )
    processes = []
    try:
        for (directory, command), name in zip(commands, ("backend", "vite"), strict=True):
            with (args.output / f"{name}.log").open("w") as log:
                processes.append(subprocess.Popen(command, cwd=directory, env=env, stdout=log, stderr=subprocess.STDOUT))
        if not args.advisory_only:
            asyncio.run(browser_check(args.chromium))
            asyncio.run(browser_risk_check(args.chromium))
        asyncio.run(browser_advisory_check(args.chromium, args.axe))
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
