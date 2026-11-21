"""Opt-in bounded public market-universe acceptance using the production owners.

Run from backend with PYTHONPATH=. and --allow-public-network. The native
WebSocket lifecycle has its own phase155b_live_readonly_acceptance.py harness.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import resource
import threading
from time import monotonic

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.market_universe import router
from app.market_data.market_universe_discovery import (
    MarketUniverseDiscovery, OfficialMetadataClient, _failure_code,
)
from app.market_data.market_summaries import MarketSummaryObservations

CORE = ("BTC", "ETH", "SOL", "DOGE")
CADENCE = 20


class MeteredClient(OfficialMetadataClient):
    def __init__(self, network, calls):
        super().__init__(network)
        self.network, self.calls = network, calls
        self.inventory_count = None

    def __call__(self, operation, dex, deadline):
        start = monotonic()
        row = {"network": self.network, "operation": operation, "dex": dex}
        try:
            data = super().__call__(operation, dex, deadline)
            if operation == "perpDexs" and isinstance(data, list):
                self.inventory_count = len(data)
            row["result"] = "OK"
            return data
        except Exception as exc:
            row["result"] = _failure_code(exc)
            raise
        finally:
            # OK implies the SDK session returned from its finally/close block.
            self.calls.append((start, row, round(monotonic() - start, 3)))


def resources(discovery, summaries):
    rss_kib = int(next(line.split()[1] for line in Path("/proc/self/status").read_text().splitlines()
                       if line.startswith("VmRSS:")))
    return {
        "rss_kib": rss_kib, "threads": threading.active_count(),
        "asyncio_tasks": len(asyncio.all_tasks()),
        "discovery_threads": sum(thread.is_alive() for thread in discovery._pool._threads),
        "summary_tasks": len(summaries._tasks), "summary_captures": len(summaries._cache),
    }


def select_keys(catalog):
    records = [item for item in catalog.records if item.listed]
    core = {item.identity.instrument_name: item.identity.stable_key
            for item in records if item.identity.dex == ""}
    xyz = [item for item in records if item.identity.dex == "xyz"]
    alternate = [item for item in records if item.identity.dex not in ("", "xyz")]
    keys = [core[coin] for coin in CORE if coin in core]
    for candidates in (xyz, alternate):
        if candidates:
            keys.append(candidates[0].identity.stable_key)
    return keys, all(coin in core for coin in CORE[:3]) and bool(xyz and alternate)


async def run(seconds):
    start = monotonic()
    calls, cycles, samples = [], [], []
    client = MeteredClient("MAINNET", calls)
    discovery = MarketUniverseDiscovery(enabled=True, network="MAINNET", client=client)
    summaries = MarketSummaryObservations("MAINNET", client=client)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.market_universe_discovery = discovery
    app.state.market_summary_observations = summaries
    report = {"started_utc": datetime.now(timezone.utc).isoformat(), "requested_seconds": seconds,
              "mainnet_cycles": cycles, "resource_samples": samples, "authority": "NONE"}
    previous = None
    try:
        samples.append({"elapsed_seconds": 0, **resources(discovery, summaries)})
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as api:
            while True:
                tick = monotonic()
                response = await api.get("/api/v1/market-universe")
                raw = response.json()
                generation = raw["catalog_fingerprint"]
                cycle = {"elapsed_seconds": round(tick - start, 3), "discovery_http": response.status_code,
                         "availability": raw["availability"], "error": raw["error"],
                         "discovery_seconds": round(monotonic() - tick, 3),
                         "generation_changed": generation != previous}
                cycles.append(cycle)
                if raw["availability"] == "AVAILABLE":
                    catalog = await discovery.catalog()
                    keys, coverage = select_keys(catalog.catalog)
                    cycle.update(keys=keys, required_coverage=coverage, namespaces=len(catalog.namespaces),
                                 records=len(catalog.catalog.records))
                    selection = {"network": "MAINNET", "catalog_fingerprint": generation, "market_keys": keys}
                    if previous and previous != generation:
                        expired = await api.post("/api/v1/market-universe/market-summaries",
                                                 json={**selection, "catalog_fingerprint": previous})
                        cycle["retired_generation_http"] = expired.status_code
                    previous = generation
                    summary_start = monotonic()
                    summary = await api.post("/api/v1/market-universe/market-summaries", json=selection)
                    rows = summary.json().get("results", [])
                    cycle.update(summary_http=summary.status_code, summary_seconds=round(monotonic()-summary_start, 3),
                                 statuses=[row["status"] for row in rows],
                                 current_mark_funding=sum(row["status"] == "CURRENT" and row["mark_price"] is not None
                                                          and row["funding_rate"] is not None for row in rows))
                    if len(cycles) == 1 and summary.status_code == 200:
                        before = len(calls)
                        for refresh in (False, True):
                            cached = await api.post("/api/v1/market-universe/market-summaries",
                                                    json={**selection, "refresh": refresh})
                            cycle[f"cache_reuse_{refresh}"] = (
                                cached.status_code == 200 and len(calls) == before
                                and [row["observation_fingerprint"] for row in cached.json()["results"]]
                                == [row["observation_fingerprint"] for row in rows]
                            )
                samples.append({"elapsed_seconds": round(monotonic()-start, 3), **resources(discovery, summaries)})
                if any(row["result"] in {"FORBIDDEN", "RATE_LIMITED", "CLEANUP_ERROR"} for _, row, _ in calls):
                    break
                if seconds == 0 or monotonic() >= start + seconds:
                    break
                await asyncio.sleep(max(0, min(tick + CADENCE, start + seconds) - monotonic()))
    finally:
        report["mainnet_elapsed_seconds"] = round(monotonic() - start, 3)
        await summaries.close()
        await discovery.close()
        report["after_owner_shutdown"] = resources(discovery, summaries)
        report["retired_on_close"] = previous is None or discovery.paper_generation(previous) is None

    testnet = MeteredClient("TESTNET", calls)
    test_discovery = MarketUniverseDiscovery(enabled=True, network="TESTNET", client=testnet)
    try:
        result = await test_discovery.catalog()
        report["testnet_catalog"] = {"availability": result.availability, "error": result.error,
                                     "inventory_error": result.inventory.error if result.inventory else None,
                                     "inventory_count": testnet.inventory_count,
                                     "published": result.catalog is not None}
        if not any(row["result"] in {"FORBIDDEN", "RATE_LIMITED", "CLEANUP_ERROR"}
                   for _, row, _ in calls):
            context = await asyncio.to_thread(testnet, "metaAndAssetCtxs", "", monotonic() + 5)
            universe, contexts = context
            report["testnet_core"] = {item["name"]: all(row.get(field) is not None
                                       for field in ("markPx", "oraclePx", "funding"))
                                      for item, row in zip(universe["universe"], contexts, strict=True)
                                      if item["name"] in CORE}
    except Exception as exc:
        report["testnet_error"] = _failure_code(exc)
    finally:
        await test_discovery.close()

    counts = Counter((row["network"], row["operation"], row["result"]) for _, row, _ in calls)
    report["call_counts"] = [{"network": net, "operation": op, "result": result, "count": count}
                             for (net, op, result), count in sorted(counts.items())]
    times = sorted(t for t, _, _ in calls)
    report["total_calls"] = len(times)
    # Use the provider's default Info weight for every attempted call as a
    # conservative estimate. This is independent of the shared IP's other traffic.
    report["weight_20_per_call_upper_bound"] = 20 * len(times)
    report["max_rolling_minute_weight_upper_bound"] = max(
        (20 * sum(t - 60 < other <= t for other in times) for t in times), default=0)
    report["max_provider_call_seconds"] = max((elapsed for _, _, elapsed in calls), default=0)
    report["process_peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report["rss_peak_increment_kib"] = max(sample["rss_kib"] for sample in samples) - samples[0]["rss_kib"]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-network", action="store_true", required=True)
    parser.add_argument("--seconds", type=int, default=1800)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 0 <= args.seconds <= 1800:
        parser.error("--seconds must be 0..1800 (zero runs one cycle)")
    report = asyncio.run(run(args.seconds))
    report["threads_after_loop_close"] = threading.active_count()
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
