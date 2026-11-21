# Phase 18.7 acceptance matrix

The reference tree is main at `46c7dd38b53616c070155896baf3f14afe7ea40f`. PR #100 is the Phase 18.6H implementation and reported acceptance. PR #101 adds the current source map. See the [A–C evidence record](PHASE18_7ABC_ACCEPTANCE.md) for independently executed results and open gates.

| Area | Current owner and trust boundary | Historical reference | Independent evidence |
| --- | --- | --- | --- |
| Operational quotes | `main.py`, `runtime.py`, `market_data/`, `amm/`, `strategy/`, `agents/`, `risk/`, `execution/` and `accounting/`. Six supervisory agents feed existing RiskFirewall and FinalQuoteAuthorization before OrderManager. | Audit 3.0 and PR #84 | A maps ownership. B reruns existing source/authority fixtures and instruments observation paths. D owns final economic and authorization review. |
| Core and HIP-3 discovery | `market_universe_contracts.py` and `market_universe_discovery.py`. Server-owned catalog binds venue, network, class, DEX, name, source coin, ordinal, size precision, listing and receipt. | PRs #85–#87 | B reruns `test_phase180a*` and `test_phase181*`. Cross-market cases select same-name Core and HIP-3 instruments and distinguish Mainnet and Testnet. |
| Public summaries | `market_summaries.py` and `api/market_universe.py` reuse `OfficialMetadataClient`. Separate catalog, metadata and observation digests. Receipts use server UTC with no upstream event time. | PR #100, 30 summary tests within 249 focused backend tests | B/C rerun `test_phase186h_market_summaries.py` and exercise network/DEX isolation, numeric and precision edges, bounded transport failures and concurrent lifecycle. Live observations are recorded separately. |
| Financial source and advisory evidence | `market_risk_metadata.py`, `market_risk_engine.py`, `advisory_market_observations.py`, `advisory_coordinator.py` and `advisory_evidence.py`. Three observational advisory agents and optional source-constrained inputs. | PRs #89–#95 | B reruns `test_phase183*` and `test_phase184*`. D owns financial and authority certification. |
| Generalized PAPER | `generalized_market_profiles.py`, `market_profiles.py`, existing `SimulationService`, `SimulationExecutor` and `engine.py`. One qualified market, synthetic reference and hypothetical accounting. | PRs #88–#89 and PR #100 standard captures | A compares fixed-clock serialized captures. B reruns `test_phase182*` and tests PAPER admission while public summary work is pending. |
| Asset-aware PAPER | `asset_policy_contracts.py` and `asset_policy.py` map operator declarations into existing AMMs and strategy controls. | PRs #96–#98 and PR #100 asset-aware captures | A compares fixed-clock serialized captures. B reruns `test_phase185*` for both AMMs, risk modes, precision, and asset-family invariance. |
| Native portfolio | `portfolio_research/`, `api/portfolio_research.py` and the same research executor. Canonical BTC/ETH/SOL subsets, isolated sequential PAPER, hypothetical allocations and modeled stress. | PRs #73–#80, Phase 17.6 financial oracle and Phase 18.2G fingerprints | B reruns `test_phase17*` and the published native fingerprint probe. Arbitrary HIP-3 portfolio participation, live balances and shared cross-DEX collateral are outside this portfolio contract. |
| Native Live Markets | `live_observations.py`, `live_streams.py`, `api/live_markets.py` and `api/live_market_streams.py`. Native BTC/ETH/SOL read-only REST and WebSockets. | Phase 15, Audit 3.0 and PR #101 map | C checks lifecycle and summary isolation from subscriptions. Full reconnect rollout remains with F. |
| Frontend | `api/client.ts`, `utils/{marketUniverse,marketSummaries,generalizedPaper,portfolioResearch}.ts`, `useMarketSummaries.ts`, `MarketExplorer.tsx`. Canonical source validation and independent presentation state. | PRs #99–#101, 949 tests and eight 18.6H Chromium workflows | B/C locked install, typecheck, Node tests, build and source-expiry coverage. E owns the cross-browser and accessibility matrix. |

## Contract inventory

All HTTP paths below are relative to `/api/v1`. Public discovery, risk, advisory and summaries do not reserve the PAPER worker.

| Entry point | Contract, bounds and failure behavior |
| --- | --- |
| `GET /market-universe` | `phase181-v1` over `phase180b-v2` records. Server chooses network. Up to 64 namespaces including Core and 4,096 records. Browser response cap 5 MB. Available, partial and stale states return 200; disabled/unavailable return 503, upstream throttle 429 with Retry-After, and timeout 504. Partial refresh can describe failed namespaces and expose previously complete stale evidence. |
| `POST /market-universe/market-summaries` | `phase186h-v1`, 1–13 unique keys, matching active catalog fingerprint and configured network. 404 unknown key, 409 retired or foreign generation, 422 invalid selection. Captures return per-row failure states with 200. Browser payload cap 32 KiB. |
| `GET /market-universe/risk-evidence` | `phase183e-v1` envelope and `phase183c-v1` model. Canonical identity and active catalog required. Metadata and financial observation fingerprints are separate. Unknown identity 404, generation/network mismatch 409, invalid identity 422. Source status can be unavailable, unsupported or stale. Browser response cap 16 KiB. |
| `POST /market-universe/advisory` | `phase184e-v1` with `phase184a-v1` context and `phase184bcd-v1` analysis. One identity per request, up to 120 quote cohorts, eight concurrent requests and three evaluations. Coordinator verifies source and receipt binding. Response cap 65,536 bytes. Bounded validation, conflict, capacity and unavailable responses. |
| `POST /generalized-paper/asset-policy/preview` | `phase185a-v1` policy from server catalog, explicit synthetic reference, operator declaration and approved controls. Preview does not execute. Structured invalid, conflict and unavailable decisions use 422, 409 and 503. |
| `POST /generalized-paper/eligibility`, `POST /generalized-paper/run` | `phase182-v1`; same server-owned profile and expected admission binding are rechecked at execution. Maximum 120 frames and 2,000,000 response bytes. Shared worker contention 429, unavailable 503. |
| `POST /portfolio-research/{preview,run,analyze,stress,terminal}` | `phase17-portfolio-research-v1`, `phase174-stress-v1` and `phase175-terminal-v1`. Preview resolves native profiles, execution operations share the existing worker. 200,000 response bytes, bounded 413/422 and 429/503. |
| `GET /live-markets/{overview,{market}/snapshot}` | `phase151-v1` native BTC/ETH/SOL snapshot and overview. 200 for usable/partial observations, 429 for capacity or backoff, 504 for timeout, 503 when unavailable. Separate native source clocks and SDK sessions. |
| `GET /live-markets/{market}/{stream-status,stream-snapshot,history,references}`, `/ws/live-markets/{market}` | `phase152-v1` native bounded stream projections, history limited to 1–1,000 rows and one service-owned SDK connection. Unsupported WebSocket market 1008, unavailable/capacity 1013. |

## Baselines and budgets

| Reference | Published evidence |
| --- | --- |
| PR #100 standard PAPER | 38 admission/result pairs, SHA-256 `b564ad46f264f8b8295feb5dc59d4c44a3e97b2302769663aaf94dbd5fbce65e` |
| PR #100 asset-aware PAPER | 18 pairs, SHA-256 `5fa22910e35da8655a6f99df148cc809a2d6043ba090c2ae051ba479e64cf47f` |
| Native PAPER and portfolio | 39 dataset fingerprints and three native receipts, combined digest `22eed4a5c0d67fa94b0e8780e9cbfd3af50276cab4e2b5e2a22e581b449a34ad`. [Published reproduction](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md#native-btcethsol-compatibility) |
| Summary acquisition | Three active namespaces, 24 captures retained, 15 s reuse, 30 s maximum observed age, 5 s minimum cached manual refresh interval, 24 starts per rolling minute, 6 s API wait budget, 30 s 429 backoff and 1 MiB provider response cap. Explorer refreshes at 20 s while visible. |
| Discovery | Three collection threads, 5 s per transport timeout, 15 s collection deadline, 60 s default catalog lifetime, 1 MiB per upstream response. Testnet inventory above 64 must fail closed. See the capacity decision in the [A–C report](PHASE18_7ABC_ACCEPTANCE.md). |
| Research worker | One admission owner for PAPER, portfolio and replay. Worker keeps its slot while admitted work runs after caller cancellation. Summary requests use the application event loop's thread executor. |

## Milestone ownership

| Milestone | Scope | Independent disposition |
| --- | --- | --- |
| 18.7A | Source and contract inventory, pinned baseline and independent compatibility results. | Source inventory and controlled byte parity verified. Exact PR #100 capture digests remain open. |
| 18.7B | Core BTC/ETH/SOL/DOGE, HIP-3 GOLD/XYZ100 and same-name DEX isolation, cross-network, listing, catalog and precision fixtures, PAPER and native portfolio compatibility. Live availability is point-in-time. | Deterministic regressions and bounded Mainnet source spot checks passed. Native digest reproduced. |
| 18.7C | Acquisition limits, transport, refresh, latency, resource use, cancellation, shutdown and bounded official provider verification. | Deterministic resilience and bounded live checks passed. Full Testnet discovery is outside the current cap. Sustained provider checks remain with rollout. |
| 18.7D | Independent financial and authority certification, including signed-venue gates. | Pending independent review. |
| 18.7E | Cross-browser, assistive technology and OS-level accessibility acceptance. | Pending browser and accessibility matrix. |
| 18.7F | Release decision, production rollout and external provider/recovery gates. | Pending release decision. |
