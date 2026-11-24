"""Opt-in public provider acceptance on Linux using the existing application owners.

The default scope measures discovery and summaries. --mixed-owners adds the
advisory and native read-only owners. Run from backend with PYTHONPATH=.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
from functools import partial
import json
from pathlib import Path
import resource
import signal
import threading
from time import monotonic
from unittest.mock import patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from hyperliquid.api import API

from app.api.market_universe import router
from app.config import Settings
from app.market_data.live_observations import classify
from app.market_data.live_streams import LiveMarketStreamService, SDKObservationClient
from app.market_data.market_universe_discovery import (
    DiscoveryFailure, MarketUniverseDiscovery, MarketUniverseResponse, OfficialMetadataClient, _failure_code,
)
from app.market_data.market_summaries import MarketSummaryObservations, MarketSummaryResponse
from app.market_data.provider_budget import HyperliquidBudget, WEIGHTS

CORE = ("BTC", "ETH", "SOL", "DOGE")
CADENCE = 20
WEIGHT_LIMIT = 900


class MeteredClient(OfficialMetadataClient):
    def __init__(self, network, calls, budget, *, owner="discovery"):
        super().__init__(network, budget=budget, owner=owner)
        self.network, self.calls = network, calls
        self.inventory_count = None

    def _send(self, session, path, payload, deadline, remaining):
        started = monotonic()
        operation = payload["type"]
        row = {"network": self.network, "operation": operation, "dex": payload.get("dex", ""),
               "started_at_utc": datetime.now(timezone.utc).isoformat()}
        try:
            data = super()._send(session, path, payload, deadline, remaining)
            if operation == "perpDexs" and isinstance(data, list):
                self.inventory_count = len(data)
            row["result"] = "OK"
            return data
        except Exception as exc:
            row["result"] = _failure_code(exc)
            raise
        finally:
            self.calls.append((started, row, round(monotonic() - started, 3)))


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
    budget = HyperliquidBudget(WEIGHT_LIMIT)
    client = MeteredClient("MAINNET", calls, budget)
    discovery = MarketUniverseDiscovery(enabled=True, network="MAINNET", client=client)
    summaries = MarketSummaryObservations("MAINNET", client=MeteredClient("MAINNET", calls, budget, owner="summary"))
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

    testnet = MeteredClient("TESTNET", calls, budget)
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


class InfoMeasurements:
    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()
        self.peak_weight = 0
        self.capped = False
        self.active = Counter()
        self.peak_active = Counter()

    def measure(self, owner, payload, call):
        operation = payload['type']
        if operation not in {'perpDexs', 'meta', 'spotMeta', 'metaAndAssetCtxs', 'l2Book', 'fundingHistory'}:
            raise DiscoveryFailure('UNSUPPORTED_METADATA')
        # The transport probe observes admitted sends, including the provider's
        # greatest documented reservation for time-range responses.
        weight = WEIGHTS[operation]
        with self.lock:
            start = monotonic()
            rolling_weight = weight + sum(row['weight'] for row in self.calls if start - row['start'] < 60)
            if rolling_weight > WEIGHT_LIMIT:
                # Keep a separate hard stop on instrumented official traffic.
                self.capped = True
                raise DiscoveryFailure('CLOSED')
            row = dict(owner=owner, operation=operation, weight=weight, start=start,
                       started_at_utc=datetime.now(timezone.utc).isoformat())
            self.calls.append(row)
            self.peak_weight = max(self.peak_weight, rolling_weight)
            self.active[owner] += 1
            self.peak_active[owner] = max(self.peak_active[owner], self.active[owner])
        try:
            result = call()
            with self.lock:
                row['status'] = 'SUCCESS'
                if operation == 'fundingHistory' and isinstance(result, list):
                    row['weight'] = 20 + (len(result) + 19) // 20
            return result
        except Exception as exc:
            with self.lock:
                row['status'] = exc.code if isinstance(exc, DiscoveryFailure) else classify(exc)
            raise
        finally:
            with self.lock:
                self.active[owner] -= 1
                row['seconds'] = round(monotonic() - start, 4)

    def totals(self):
        with self.lock:
            return {
                'starts': len(self.calls), 'weight': sum(row['weight'] for row in self.calls),
                'peak_rolling_60s_weight_upper_bound': self.peak_weight, 'guard_triggered': self.capped,
                'peak_active': dict(self.peak_active), 'owners': {
                    owner: {'starts': len(calls), 'weight': sum(row['weight'] for row in calls),
                            'operations': dict(Counter(row['operation'] for row in calls)),
                            'statuses': dict(Counter(row.get('status', 'IN_FLIGHT') for row in calls)),
                            'max_seconds': max((row.get('seconds', 0) for row in calls), default=0)}
                    for owner in self.peak_active
                    if (calls := [row for row in self.calls if row['owner'] == owner])
                },
            }


def selected_records(catalog):
    eligible = {row.identity.stable_key for row in catalog.eligibility if row.discovery_eligible}
    supported = [row for row in catalog.catalog.records if row.identity.stable_key in eligible]
    core = {row.identity.exchange_coin: row for row in supported if not row.identity.dex}
    xyz = next((row for row in supported if row.identity.dex == 'xyz'), None)
    other = next((row for row in supported if row.identity.dex not in ('', 'xyz')), None)
    if set(CORE) <= core.keys() and xyz and other:
        return (*[core[coin] for coin in CORE], xyz, other)
    return ()


def mixed_resources(started):
    with Path('/proc/self/status').open() as status:
        values = dict(line.split(':', 1) for line in status if ':' in line)
    return {'elapsed_seconds': round(monotonic() - started, 2),
            'rss_kib': int(values['VmRSS'].split()[0]), 'os_threads': int(values['Threads']),
            'process_peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'python_threads': threading.active_count()}


def write(output, report):
    temporary = output.with_name(output.name + '.tmp')
    temporary.write_text(json.dumps(report, indent=2) + '\n')
    temporary.replace(output)


async def poll_market(client, state, report, cycle, generations):
    start = monotonic()
    response = await client.get('/api/v1/market-universe')
    catalog = MarketUniverseResponse.model_validate_json(response.content)
    cycle.update(discovery_http=response.status_code, discovery=catalog.availability,
                 discovery_seconds=round(monotonic() - start, 3))
    if catalog.availability != 'AVAILABLE':
        return
    generations.add(catalog.catalog_fingerprint)
    cycle['catalog_records'] = len(catalog.catalog.records)
    records = selected_records(catalog)
    if not records:
        return
    body = {'network': 'MAINNET', 'catalog_fingerprint': catalog.catalog_fingerprint,
            'market_keys': [row.identity.stable_key for row in records]}
    start = monotonic()
    response = await client.post('/api/v1/market-universe/market-summaries', json=body)
    cycle.update(summary_http=response.status_code, summary_seconds=round(monotonic() - start, 3))
    if response.is_success:
        summary = MarketSummaryResponse.model_validate_json(response.content)
        cycle['summary_statuses'] = dict(Counter(row.status for row in summary.results))
        cycle['summary_errors'] = dict(Counter(row.error for row in summary.results if row.error))
        if all(row.status == 'CURRENT' and row.mark_price and row.funding_rate is not None for row in summary.results):
            report['complete_summary_polls'] += 1
            if not report['observations']:
                report['observations'] = [{'coin': row.identity.exchange_coin, 'mark': row.mark_price,
                    'oracle': row.oracle_price, 'funding': row.funding_rate, 'observed_at': row.observed_at.isoformat(),
                    'valid_until': row.valid_until.isoformat(), 'metadata_fingerprint': row.metadata_fingerprint}
                    for row in summary.results]
        receipts = tuple(row.observed_at for row in summary.results)
        if not report['cache_reuse'] and all(receipts):
            repeat = await client.post('/api/v1/market-universe/market-summaries', json=body)
            if repeat.is_success:
                cached = MarketSummaryResponse.model_validate_json(repeat.content)
                report['cache_reuse'] = receipts == tuple(row.observed_at for row in cached.results)
    if not report['advisory']:
        market = records[-1]
        capture = await state.advisory_coordinator._observations.observe(
            market,
            financial=state.market_universe_discovery.financial_observation(catalog.catalog_fingerprint, market.identity),
            namespace_records=tuple(sorted(
                (record for record in catalog.catalog.records if record.identity.dex == market.identity.dex),
                key=lambda record: record.universe_index,
            )),
            catalog_fingerprint=catalog.catalog_fingerprint,
        )
        report['advisory'] = {'coin': records[-1].identity.exchange_coin, 'status': capture.status,
                              'categories': sorted(point.category for point in capture.points)}


async def soak(args, report, started):
    from app import main as release_app

    measured = InfoMeasurements()
    official_send, sdk_post = OfficialMetadataClient._send, API.post
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    def official(self, session, path, payload, deadline, remaining):
        return measured.measure(self.owner, payload,
                                lambda: official_send(self, session, path, payload, deadline, remaining))

    def sdk(self, path, payload=None):
        if path != '/info' or payload is None:
            raise DiscoveryFailure('UNSUPPORTED_METADATA')
        owner = getattr(self, '_soak_owner', 'native_rest')
        if callable(owner):
            owner = owner()
        return measured.measure(owner, payload, lambda: sdk_post(self, path, payload))

    bind_sdk = HyperliquidBudget.bind_sdk

    def instrument_binding(self, info, owner, timeout, **kwargs):
        info._soak_owner = owner
        return bind_sdk(self, info, owner, timeout, **kwargs)

    connections = []

    class ObservedSDK(SDKObservationClient):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            connections.append(self)

    release_app.settings = Settings(_env_file=None, market_data_mode='DEMO', execution_mode='PAPER',
                             market_universe_enabled=True, market_universe_network='MAINNET',
                             live_observations_enabled=True, live_streams_enabled=True,
                             enable_hyperliquid_testnet_orders=False, redis_enabled=False,
                             redis_required=False, redis_research_enabled=False, redstone_enabled=False,
                             kraken_reference_enabled=False, coingecko_reference_enabled=False,
                             yfinance_reference_enabled=False)
    generations = set()
    report['resource_samples'].append(mixed_resources(started))
    with (patch.object(release_app, 'LiveMarketStreamService', partial(LiveMarketStreamService, client_factory=ObservedSDK)),
          patch.object(OfficialMetadataClient, '_send', official), patch.object(API, 'post', sdk),
          patch.object(HyperliquidBudget, 'bind_sdk', instrument_binding)):
        app = release_app.app
        async with app.router.lifespan_context(app):
            state = app.state
            streams = state.live_market_streams
            async with AsyncClient(transport=ASGITransport(app=app), base_url='http://127.0.0.1:8000') as client:
                next_poll = workload_start = monotonic()
                deadline = workload_start + args.seconds
                while not stop.is_set() and not measured.capped and monotonic() < deadline:
                    cycle = {'elapsed_seconds': round(monotonic() - started, 2)}
                    report['polls'].append(cycle)
                    await poll_market(client, state, report, cycle, generations)
                    if not report['native_rest']:
                        native = await state.live_market_observer.overview()
                        report['native_rest'] = {row.market: row.observation_status for row in native.markets}
                    statuses = {coin: streams.snapshot(coin) for coin in CORE[:3]}
                    current = all(snapshot.observation_status == 'AVAILABLE' for snapshot in statuses.values())
                    cycle.update(native_current=current, native_generation=streams._generation,
                                 native={coin: {'l2_age_seconds': snapshot.status.l2_age_seconds,
                                                'context_age_seconds': snapshot.status.perp_age_seconds,
                                                'metadata_age_seconds': snapshot.status.metadata_age_seconds,
                                                'availability': snapshot.observation_status,
                                                'error': snapshot.status.last_error_code,
                                                'gap_count': streams.history.query(coin).gap_count}
                                         for coin, snapshot in statuses.items()})
                    if current:
                        report['native_current_polls'] += 1
                        if report['controlled_disconnect_generation'] is None:
                            report['controlled_disconnect_generation'] = streams._generation
                            await streams._call(streams._client.info.ws_manager.ws.close)
                        elif streams._generation > report['controlled_disconnect_generation']:
                            report.setdefault('controlled_reconnect_generation', streams._generation)
                    if len(report['polls']) % 3 == 1:
                        sample = mixed_resources(started)
                        sample.update(async_tasks=len(asyncio.all_tasks()),
                                      sdk_subscriptions=sum(len(item.handles) for item in connections),
                                      local_subscribers=len(streams._subscribers),
                                      summary_cache=len(state.market_summary_observations._cache))
                        report['resource_samples'].append(sample)
                        report['request_metrics'] = measured.totals()
                        snapshot = state.hyperliquid_budget.metrics()
                        sample['provider_rolling_weight'] = snapshot['rolling_weight']
                        sample['provider_active'] = snapshot['active']
                        sample['provider_waiting'] = snapshot['waiting']
                        write(args.output, report)
                    next_poll = max(next_poll + CADENCE, monotonic())
                    try:
                        await asyncio.wait_for(stop.wait(), max(0, min(next_poll, deadline) - monotonic()))
                    except TimeoutError:
                        pass
                report['workload_seconds'] = round(monotonic() - workload_start, 3)
        report['cleanup'] = {
            'native_sdk_client_starts': len(connections),
            'native_sdk_sessions_or_handles_remaining': sum(bool(item.info or item.bootstrap or item.handles) for item in connections),
            'native_local_subscribers_remaining': len(streams._subscribers),
            'native_owned_threads_remaining': sum(thread.is_alive() for thread in streams._pool._threads),
            'native_owned_tasks_remaining': sum(bool(task and not task.done()) for task in (streams._runner, streams._close_task)),
            'native_fresh_components_remaining': sum(status == 'FRESH' for coin in CORE[:3] for status in (
                streams.snapshot(coin).status.l2_freshness, streams.snapshot(coin).status.perp_freshness)),
            'discovery_threads_remaining': sum(thread.is_alive() for thread in state.market_universe_discovery._pool._threads),
            'summary_captures_remaining': len(state.market_summary_observations._cache),
            'summary_tasks_remaining': len(state.market_summary_observations._tasks),
        }
    budget = state.hyperliquid_budget.metrics()
    budget['counts'] = {'.'.join(key): value for key, value in budget['counts'].items()}
    report.update(distinct_catalog_generations=len(generations), request_metrics=measured.totals(),
                  requests=measured.calls, budget=budget, interrupted=stop.is_set())
    if any(value for key, value in report['cleanup'].items() if key.endswith('_remaining')):
        report['classification'] = 'FAIL'
    elif (not stop.is_set() and not measured.capped and report['workload_seconds'] >= args.seconds
          and report['complete_summary_polls'] >= 2 and report['native_current_polls'] >= 2
          and report.get('controlled_reconnect_generation') and len(generations) >= 2 and report['cache_reuse']):
        report['classification'] = 'PASS'
    else:
        report['classification'] = 'CONDITIONAL'


def run_mixed(args):
    started = monotonic()
    report = {'classification': 'RUNNING', 'evidence': 'ACTUAL PUBLIC MAINNET, LOCAL DEMO/PAPER',
              'started_at': datetime.now(timezone.utc).isoformat(), 'target_seconds': args.seconds,
              'poll_seconds': CADENCE, 'polls': [], 'resource_samples': [], 'observations': [],
              'complete_summary_polls': 0, 'native_current_polls': 0, 'cache_reuse': False,
              'advisory': {}, 'native_rest': {}, 'controlled_disconnect_generation': None}
    try:
        asyncio.run(soak(args, report, started))
    except Exception as exc:
        report.update(classification='FAIL', error_type=type(exc).__name__)
        raise
    finally:
        report['elapsed_seconds'] = round(monotonic() - started, 3)
        report['resource_samples'].append(mixed_resources(started))
        write(args.output, report)
    return 0 if report['classification'] == 'PASS' else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-public-network', action='store_true', required=True)
    parser.add_argument('--mixed-owners', action='store_true',
                        help='Measure discovery, summaries, advisory and native observers together')
    parser.add_argument('--seconds', type=int, default=1800)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    minimum = 60 if args.mixed_owners else 0
    if not minimum <= args.seconds <= 1800:
        parser.error(f'--seconds must be {minimum}..1800')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.mixed_owners:
        return run_mixed(args)
    report = asyncio.run(run(args.seconds))
    report['threads_after_loop_close'] = threading.active_count()
    write(args.output, report)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
