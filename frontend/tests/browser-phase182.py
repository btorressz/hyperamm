"""Chromium against the real API and worker with read-only metadata fixtures."""
import argparse
import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def fixture_app():
    from app.main import app
    from app.market_data.market_universe_discovery import MarketUniverseDiscovery

    def provider(method, dex, deadline):
        if method == "perpDexs":
            return [None, {"name": "xyz"}]
        rows = ([{"name": "xyz:GOLD", "szDecimals": 3}] if dex else
                [{"name": "DOGE", "szDecimals": 2}, {"name": "OLD", "szDecimals": 2, "isDelisted": True}])
        return {"universe": rows}

    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(instance):
        async with original(instance):
            previous = instance.state.market_universe_discovery
            discovery = MarketUniverseDiscovery(enabled=True, network="MAINNET", client=provider)
            instance.state.market_universe_discovery = discovery
            try:
                yield
            finally:
                instance.state.market_universe_discovery = previous
                await discovery.close()

    app.router.lifespan_context = lifespan
    return app


async def browser_check(chromium):
    from playwright.async_api import async_playwright, expect

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=chromium, args=["--no-sandbox"])
        try:
            page = await browser.new_page()
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
                await expect(page.get_by_text(f"Simulated PAPER result for {coin}", exact=False)).to_be_visible()
                await expect(page.get_by_text("Net P&L in hypothetical quote units")).to_be_visible()
                print(f"PASS {coin} completes through the real worker with synthetic labeling", flush=True)
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
            assert writes and all("/api/v1/generalized-paper/" in url for url in writes), writes
            print("PASS native selection preserved and write requests confined to PAPER", flush=True)
        finally:
            await browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True)
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    parser.add_argument("--output", type=Path, required=True)
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
        asyncio.run(browser_check(args.chromium))
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
