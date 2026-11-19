# Phase 18.2G final PAPER hardening acceptance

## Baseline and pre-edit findings

The baseline is `main` at `b2163b5331d2a7b823475783a01105bd7d5a441a`, the merge of PR #88. The review traced the first-parent changes and case coverage back through #84 (`14dfde7`), #85 (`115f138`), #86 (`ac1bfcf`) and #87 (`8f9e695`). It followed the generalized proposal through discovery, admission, scenario construction, reference aggregation, agents, Risk Firewall, matching, accounting, result validation and the React workspace. [Audit 3.0](../AUDIT_REPORT_3.0.md) · [Final remediation](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md) · [18.0 architecture](PHASE18_0_MARKET_UNIVERSE_ARCHITECTURE.md) · [18.0B](PHASE18_0B_ACCEPTANCE.md) · [18.1](PHASE18_1_DISCOVERY_ACCEPTANCE.md) · [18.2](PHASE18_2_PAPER_ACCEPTANCE.md)

| Classification | Baseline finding | Disposition |
| --- | --- | --- |
| Confirmed defect | A quiet scenario produced a `VERIFIED` quorum from provider-shaped synthetic inputs. All six `source_timestamp` values equaled frame time. Ordinary consensus reproduced the verified state using those observations. | Bind scenario provenance at frame creation, use synthetic identities through consensus and agents, leave provider acquisition time absent, and fence operational consumers. |
| Confirmed defect | A delayed worker could start from the selected record after the server replaced the complete catalog. The API also treated the exact deadline as eligible while the frontend retired it. | Bind the whole generation, retire its process-local guard when refresh starts, and use an exclusive end to the admission window. |
| Confirmed defect | Background discovery replacement or failure could retain prior admission or results when a selected row still appeared available. A new run could leave the old successful result visible during loading. | Retire bound state on catalog change, network change and failure. Clear old results at request start and guard against late responses. |
| Ambiguous evidence | Descriptive limitations and `HYPOTHETICAL_LINEAR_ONLY` left reservation policy, financial units, scheduled funding and future risk compatibility implicit. The result omitted the simulation start time. | Add a typed scope to the existing profile and report the actual local engine start in the result. |
| Missing safeguards and tests | Tests covered basic stale snapshots and per-record changes. They did not cover a different whole generation with the same selected row, forged provider provenance, exact start deadlines, or the fee and lifecycle cases listed below. | Add focused backend and browser regressions. |
| Existing correct behavior | Discovery is read-only and network-qualified. A server-owned complete generation supplies market metadata. The local engine owns simulated fills and accounting. The shared executor shields capacity until completion, and portfolio allocation is restricted to BTC/ETH/SOL. | Reuse current contracts and execution. Compare native results against #88. |
| Deferred | Exchange collateral, product-specific initial and maintenance margin, liquidation, leverage, settlement, cross-market risk and venue execution require independent contracts and evidence. | Carry forward the research compatibility boundary below. |

## Reference provenance and isolation

Generalized scenario frames use versioned `phase182g-v1:synthetic-scenario` reference inputs and a simulated perpetual context with source `GENERALIZED_PAPER`. Legacy numeric field names remain inside the scenario model. The builder maps them into six `SCENARIO_*` identities and emits `SYNTHETIC_SCENARIO` evidence with simulated transport. A frame time can describe generation and consensus evaluation. Provider acquisition time is null. The dataset fingerprint covers the frame origin and perpetual source.

The existing median, quorum, disagreement and outlier rules run on the synthetic channels. Nominal agreement emits `SYNTHETIC_AGREEMENT`. Degradation, conflict and insufficient input retain their policy meaning under synthetic provenance. Provider-specific price fields in the consensus are null. Agent and fill evidence keep the scenario IDs and provenance. Only the isolated generalized firewall recognizes scenario agreement for local recovery, and local authorization fingerprints cover the marked reference snapshot. The result trace and profile retain the synthetic interpretation. [Scenario model](../backend/app/simulation/models.py) · [Consensus](../backend/app/references/consensus.py) · [Agent evidence](../backend/app/agents/evidence.py) · [Firewall](../backend/app/risk/firewall.py)

Ordinary consensus excludes the synthetic channels even when provider-shaped keys or copied provider IDs are supplied. Reference service publication and terminal snapshot validation reject generalized evidence, and default firewall and quote authorization reject it before evaluating operational inputs. The generated operational terminal schema retains its existing wire contract. The PAPER route depends on read-only discovery and the local research worker. Tests guard Exchange construction, order/bulk-order, modification, cancellation, guarded adapter methods and wallet-key derivation with zero allowed calls. Redis coordination mirrors results only under the existing research keys. [Reference service](../backend/app/references/service.py) · [Terminal contract](../backend/tests/test_audit_terminal_contract.py) · [Isolation tests](../backend/tests/test_phase182g_paper_hardening.py)

## Financial evidence and Phase 18.3 compatibility

| Evidence | Interpretation and permitted consumption |
| --- | --- |
| Canonical market identity, network, perpetual class, DEX and instrument name | Research identity and exact namespace, including when names coincide. |
| Official catalog metadata, its observation time and the admitted size precision | Exchange-observed listing, ordinal and precision for that observation. Check catalog binding and freshness independently when using current metadata. |
| Profile version, `evidence_boundary.version`, assumptions and fingerprints | Versioned, single-market research inputs and reproducibility evidence. Fingerprints identify content and bindings. |
| Synthetic scenario pricing, depth, mark, oracle, funding rates and frame time | Deterministic simulation inputs. Source freshness and agreement describe scenario quality. The order book represents input depth for policies and crossing-only matching. |
| Starting equity, cash, base inventory, average cost, realized and unrealized P&L | Isolated hypothetical linear accounting. Quote values use `HYPOTHETICAL_QUOTE` units. Inventory uses base quantity. Equity is initial simulation capital plus modeled net P&L. |
| Maker/taker fees and scheduled funding | `HYPOTHETICAL_MAKER_TAKER` and `HYPOTHETICAL_SCHEDULED`. Fees are booked at configured bps. Signed funding uses synthetic rate, current signed quantity and mark at the configured boundary. |
| Position/order reservation and capital utilization | `SIMULATED_FULL_NOTIONAL`. The existing calculation reserves marked position notional and effective order notional, with same-slot overlap handled by the existing accounting policy. Projected inventory and capital utilization are local risk limits. |
| Collateral, exchange equity and balances, initial and maintenance margin, liquidation, leverage, settlement, verified fees and funding | `exchange_economics=UNVERIFIED`. The local firewall receives no liquidation estimate. The profile carries no verified model for these capabilities. |
| Portfolio allocation, cross-market exposure and cross-currency netting, HIP-3 operational execution, TESTNET/live authority | `risk_readiness=SINGLE_MARKET_RESEARCH_ONLY`, `scope=LOCAL_PAPER_ONLY`, `authority=NONE` and `execution_eligible=false`. Future support requires separate evidence and typed contracts. |

The profile boundary contributes to its fingerprint. The API binds that profile, the selected metadata and whole catalog, the normalized proposal, simulation engine version, dataset and effective strategy, risk, agent and accounting configurations. The result fingerprint binds the configuration, proposal and result. The server records admission evaluation and engine start separately from the scenario clock so repeated runs remain reproducible. Unsupported request fields and mutated authority claims fail validation. Native portfolio inputs reject canonical generalized markets and hypothetical accounting currency. [Profile and result contracts](../backend/app/simulation/generalized_market_profiles.py) · [Native portfolio contracts](../backend/app/portfolio_research/models.py)

## Financial and scenario matrix

| Area | Exercised evidence |
| --- | --- |
| Asset fixtures | Core crypto, HIP-3 crypto, commodity-linked, energy-linked and equity-linked hypothetical instruments complete with deterministic fingerprints. Fixture coverage is limited to synthetic products and economics. |
| Precision | Size decimals 0–6, low/high prices, magnitude-dependent and significant-figure transitions, tiny quantities, zero lots, infeasible depth, positive ordering, directional rounding and conservative exact notional. |
| Fees | Zero and maximum 100 bps. Realized simulated maker fees reconcile at the bound. Maker/taker rates are compared with direct simulated fills through the same ledger because the ordinary crossing-only passive fixture generates maker fills. |
| Funding | Positive and negative rate stress, long/short signed cashflow, interval boundaries, zero-fill funding, and repeated multi-frame high-volatility fills. |
| Accounting | Initial and ending equity, signed fill inventory, chronological ledger deltas, realized/unrealized P&L, funding, fees and full-notional reservation. |
| Quote lifecycle | Flat, long and short states, configured limits, same-price rounded duplicate handling and infeasible proposals. Losing the synthetic quorum retires all outstanding quotes, then healthy scenario agreement allows recovery through the existing confirmation policy. Resulting active quotes are positive and noncrossing. |

The 13 original HIP-3 fixture scenarios were also replayed on both trees with 40 frames, anchor 999.99, size precision 3, maker/taker 100/17 bps and a three-second funding interval. All financial projections agreed exactly. The combined hash of metrics, orders, fills, vault, ledger, accounting fingerprint and trace with the reference confidence label omitted is `d8f69fe679a304ec53face04fba24059d3a6a58942eaaaeb623d7c1bace4e713`. Generalized dataset, profile, configuration and result identities intentionally change when their provenance changes. Arithmetic and execution assumptions carry forward from #88. [Phase 18.2 tests](../backend/tests/test_phase182_generalized_paper.py) · [Phase 18.2G tests](../backend/tests/test_phase182g_paper_hardening.py)

## Admission, refresh and concurrency

- Fresh admission just before expiry passes. The exact deadline fails before dispatch or before engine start, including expiry during worker-side preflight. A run that crosses the deadline after starting retains its start and original observation evidence.
- A current complete generation is captured through the existing discovery owner. Its earliest observation bounds the generation deadline. Refresh retires the old guard before collection starts. A completed new generation with an unchanged selected row still invalidates old bindings when the catalog contents differ. A worker delayed across replacement rejects before engine entry.
- Timestamp refresh, changed precision, delisting, missing catalogs, stale retained rows, partial refresh, unsupported envelope or catalog version, network or DEX mismatch, configuration or profile tampering, and an engine-version change are covered.
- Concurrent eligibility shares discovery. Concurrent run requests contend for one slot. Cancelling an ASGI waiter leaves a running job in ownership. Both the local and fakeredis-coordinated implementations drain it during shutdown, with zero duplicate engine starts and a released lease. No client boolean, external admission object or risk-ready marker participates in server admission.

[Discovery ownership](../backend/app/market_data/market_universe_discovery.py) · [PAPER routes](../backend/app/api/market_universe.py) · [Race tests](../backend/tests/test_phase182g_paper_hardening.py)

## Frontend acceptance

The existing Simulation tab shows Core/HIP-3 classification, network-qualified identity, profile version, observation time and eligibility deadline. Results show synthetic reference and depth, modeled maker/taker fees, funding cadence, simulated equity, realized/unrealized/net P&L, inventory and full-notional reservation. Financial limitations sit beside the values. The result disclosure distinguishes engine start from scenario time and carries the fingerprint.

Chromium exercises actual Core and HIP-3 API and worker paths, rejection and expiry, input and market changes, explicit refresh, background refresh failure, automatic network replacement, accessible progress and error messages, and retirement of previous results when a run fails. The 390 px check measures overflow and uses the keyboard to open provenance. The existing native selector remains available. The generalized panel exposes only research actions, and intercepted write requests target the PAPER endpoints. [Browser harness](../frontend/tests/browser-phase182.py)

## Native BTC/ETH/SOL compatibility

Compared both trees with the same environment and fixture. The 39 native dataset fingerprints match. Three 40-frame captures use BTC and ETH `FLASH_MOVE`, SOL `HIGH_VOLATILITY`, fees of 7/13 bps and two-second funding. Full result and receipt fingerprints, profiles, strategies, AMM and quote outputs, risk decision and reference evidence, fills, ledger, fees, funding, inventory, P&L and portfolio reconciliation match. The risk comparison excludes the pre-normalization wall-clock `created_at`; the deterministic result already uses the frame clock.

| Market | Fees | Funding | Ending inventory | Net P&L |
| --- | ---: | ---: | ---: | ---: |
| BTC | 1.649680417 | -0.00023824750 | 0.03925 | -99.85197866450000000000000012 |
| ETH | 6.597695846 | -0.00095590440 | 3.1548 | -355.5188317503999999999999973 |
| SOL | 0.75101705 | 0.0110428360 | -7.21 | 5.061525786000000000000000019 |

Dataset matrix digest `e97b675557f104e1ad2bfe3713133db88c20dbc2eece9e71a3d7ed4467f05abe`. Portfolio receipt/evidence/reconciliation digest `e51a1579d079429ed6ee123e120a7d46bc38f4ebd73e7c90283ff97ab53c9417`. Combined digest `22eed4a5c0d67fa94b0e8780e9cbfd3af50276cab4e2b5e2a22e581b449a34ad`.

<details>
<summary>Reproduce the native comparison</summary>

Run the same Python probe in both trees with their respective `backend:backend/tests` on `PYTHONPATH`. Compare the three hashes and per-market evidence with `diff -u`. Use `git worktree add --detach work/phase182g-base b2163b5331d2a7b823475783a01105bd7d5a441a` for the PR #88 baseline.

```python
import asyncio
import json

from app.accounting.config import AccountingConfig
from app.risk.firewall import RiskFirewall
from app.simulation.models import stable_fingerprint
from app.simulation.scenarios import ScenarioName, generate_scenario
from app.simulation.service import SimulationService
from app.strategy.quote_engine import QuoteEngine
from phase172_fixtures import AMOUNTS, portfolio, standalone
from phase173_fixtures import native


async def main():
    config = portfolio(frames=40, scenario={"BTC": "FLASH_MOVE", "ETH": "FLASH_MOVE", "SOL": "HIGH_VOLATILITY"}, overrides={
        market: {"simulation": {"accounting": AccountingConfig(
            paper_initial_equity_quote=AMOUNTS[market], paper_fee_model_enabled=True,
            paper_maker_fee_bps="7", paper_taker_fee_bps="13",
            paper_funding_accounting_enabled=True, paper_funding_interval_seconds=2).model_dump(mode="json")}}
        for market in ("BTC", "ETH", "SOL")
    })
    engine_outputs, risk_evidence = [], []
    quotes, evaluate = QuoteEngine.generate_perp_market_adaptive, RiskFirewall.evaluate

    def record_quotes(self, *args, **kwargs):
        output = quotes(self, *args, **kwargs)
        engine_outputs.append(output[:3])
        return output

    def record_risk(self, **inputs):
        decision = evaluate(self, **inputs)
        risk_evidence.append((inputs["refs"], decision.model_dump(exclude={"created_at"})))
        return decision

    QuoteEngine.generate_perp_market_adaptive = record_quotes
    RiskFirewall.evaluate = record_risk
    datasets, markets = {}, {}
    for leg in config.scenarios:
        profile = leg.captured.inputs().market_profile
        start = len(engine_outputs)
        receipt = await standalone(SimulationService(), leg)
        result = receipt.result
        vault = result.vault
        datasets[leg.market] = {name.value: generate_scenario(
            name, frames=40, market=leg.market, market_profile=profile).fingerprint for name in ScenarioName}
        markets[leg.market] = {
            "profile": profile.profile_fingerprint, "strategy": result.strategy_fingerprint,
            "dataset": result.dataset_fingerprint, "run": result.run_fingerprint,
            "result": stable_fingerprint(result), "receipt": stable_fingerprint(receipt.provenance),
            "fills": stable_fingerprint(result.fills), "ledger": stable_fingerprint(result.accounting_ledger),
            "amm": stable_fingerprint(engine_outputs[start:]), "risk": stable_fingerprint(risk_evidence[start:]),
            "fees": str(vault.fees_quote), "funding": str(vault.funding_quote),
            "inventory": str(vault.position_base), "pnl": str(vault.net_pnl_quote),
        }
    _, legs, evidence, aggregation = await native(config)
    print(json.dumps({"datasets": stable_fingerprint(datasets), "markets": markets,
        "portfolio": stable_fingerprint((legs, evidence, aggregation)),
        "comparison": stable_fingerprint((datasets, markets, legs, evidence, aggregation))}, sort_keys=True))


asyncio.run(main())
```

</details>

## Executed checks

| Check | Actual result |
| --- | --- |
| Focused Phase 18.2, Phase 18.2G and terminal schema regression | **80 passed** in 20.11 s. Includes 26 new hardening cases. |
| Targeted backend regression | **1,764 passed**, 2 existing warnings in 751.00 s. Covers Phase 18 contracts and discovery, generalized and native profiles, scenarios, AMM and quote normalization, PAPER accounting, Risk Firewall, portfolio, worker coordination, guarded TESTNET fixtures and Audit 3.0. |
| Complete backend regression | **3,599 passed**, zero failed or skipped, 2 existing warnings in 845.94 s. The optional ML coefficient-export test ran. |
| Locked frontend install, typecheck, tests and production build | **836 tests passed**, zero failures, skips and cancellations. Locked install, typecheck and Vite build passed. |
| Chromium Generalized PAPER | **10 workflows passed** on the final source. |
| Chromium Historical Replay and Portfolio | **16 Replay** and **22 Portfolio** workflows passed. |
| Chromium Extended Scenario vs Historical | **29 workflows passed** with 60-second Playwright page/route waits, zero unexpected console errors or network failures. At the default 20-second page timeout the first run stopped during the 1,000-frame comparison, and the second stopped while waiting for the subsequent malformed-clock injection to be rejected. The 60-second rerun exercised both conditions. |
| npm dependency audit | **Zero findings** with both the full and production-only dependency trees. |
| Generalized maximum-frame probe | Two 120-frame HIGH_VOLATILITY fixtures with 100 bps fees and one-second funding completed. Core DOGE at 0.1234 and HIP-3 xyz:GOLD at 999.99 produced 189 and 210 simulated fills. Responses were 850,508 and 864,685 bytes against the 2 MB budget. |
| Compatibility | Native whole-evidence diff and 13-scenario generalized financial diff both empty against PR #88. |

Backend and frontend commands, from the repository root with the test environment activated.

```sh
(
  cd backend
  python -m pytest -q -rs --tb=short tests/test_audit_terminal_contract.py \
    tests/test_phase182g_paper_hardening.py tests/test_phase182_generalized_paper.py
  python -m pytest -q -rs --tb=short tests/test_phase18*.py tests/test_audit3*.py \
    tests/test_amm.py tests/test_execution.py tests/test_phase8*.py \
    tests/test_phase10*.py tests/test_phase11*.py tests/test_phase146_research_markets.py \
    tests/test_phase17*.py tests/test_redis_infrastructure.py
  python -m pytest -q -rs --tb=short
)
(
  cd frontend
  npm ci && npm run typecheck && npm test && npm run build
  npm audit --json
  npm audit --omit=dev --json
)
```

Run the Chromium harnesses serially because they share local ports.

```sh
python frontend/tests/browser-phase182.py --python "$(command -v python)" --output work/phase182g/paper
python frontend/tests/browser-phase1641.py --python "$(command -v python)" --output work/phase182g/replay
python frontend/tests/browser-phase176.py --python "$(command -v python)" --output work/phase182g/portfolio
python frontend/tests/browser-phase165c2.py --python "$(command -v python)" \
  --phase165d --phase166a --phase166c --phase166d --output work/phase182g/comparison
```

<details>
<summary>Reproduce the comparison timeout allowance</summary>

Save the following runner to `work/phase182g/run_comparison.py` and pass the same comparison command and flags after the runner filename, starting with `frontend/tests/browser-phase165c2.py`.

```python
"""Run the repository harness with a larger Playwright timeout on this runner."""
from pathlib import Path
import runpy
import sys

from playwright.async_api import Page, Route

harness = Path(sys.argv.pop(1)).resolve()
sys.path.insert(0, str(harness.parent))
set_default_timeout = Page.set_default_timeout
fetch = Route.fetch


def generous_default(page, timeout):
    return set_default_timeout(page, max(60000, timeout))


async def generous_fetch(route, **options):
    options.setdefault("timeout", 60000)
    return await fetch(route, **options)


Page.set_default_timeout = generous_default
Route.fetch = generous_fetch
sys.argv[0] = str(harness)
runpy.run_path(str(harness), run_name="__main__")
```

</details>

The Python regressions report the existing Starlette TestClient HTTPX deprecation and the deliberate invalid-concentration Pydantic serializer warning. Frontend checks report the existing Zustand test storage, TanStack client directive and bundle size notices.

The Python environment used CPython 3.12.14, FastAPI 0.142.2, Starlette 1.7.0, Pydantic 2.13.5, pytest 8.4.2, Hyperliquid SDK 0.24.0, Redis client 6.4.0, fakeredis 2.40.0 and scikit-learn 1.9.1. Frontend verification used Node 24.19.0, npm 11.9.0, TypeScript 5.9.3, Playwright 1.65.2 and Chromium 151.0.7922.173.

## Audit 3.0 gates and decision

A3-001 through A3-005 and A3-007 retain their scoped remediation dispositions. A3-006 retains the measured scope from Audit 3.0, with additional keyboard and narrow-width checks for Generalized PAPER. A3-008 retains the original Vite remediation. The current full and production dependency audits report zero findings for the unchanged lockfile. Prior registry-dependent results remain historical.

The earlier partial or external gates remain open in their recorded scope. These include signed TESTNET reconciliation, durable job and financial recovery, wider-market and Mainnet execution, actual venue-cost policy, provider lifecycle and failover soak, authenticated historical datasets and licensing, cross-platform lifecycle and assistive-technology acceptance, and Python dependency resolution. Phase 18.1's full Testnet catalog capacity and naming limitations remain. This milestone used deterministic metadata and economics fixtures for its new acceptance.

**PASS for Phase 18.3 development.** The Phase 18.3 handoff is bounded to development of independent market-specific collateral, margin, exposure and risk contracts. Production readiness and real exchange margin and order acceptance remain gated. [Audit gates](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md#remaining-limits-and-verdict) · [Discovery gates](PHASE18_1_DISCOVERY_ACCEPTANCE.md#readiness-and-open-gates)
