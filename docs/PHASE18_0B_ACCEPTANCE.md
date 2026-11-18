# Phase 18.0B independent acceptance

Baseline `115f1383516aa2d6f93212e81b976c2696665c75` is the merge of PR #85. Its first parent is the PR #84 Audit 3.0 remediation merge `14dfde775c0ce1a3b5517b9db6c9c4fafb48c1de`. The diff from #84 contains the isolated universe contracts, their test module, the architecture handoff and the changelog. The architecture records the final field, authority and integration boundaries. [PR #85](https://github.com/btorressz/hyperamm/pull/85) · [PR #84](https://github.com/btorressz/hyperamm/pull/84) · [Audit Report 3.0](../AUDIT_REPORT_3.0.md) · [Architecture](PHASE18_0_MARKET_UNIVERSE_ARCHITECTURE.md)

## Findings before editing

| Classification | Finding | Disposition |
| --- | --- | --- |
| Confirmed defect | Catalog admission accepted copied metadata with an invalid status or negative index and nested identities with a forged venue. Direct decision revalidation accepted a copied PAPER flag. | Revalidate instances recursively, including at fingerprint and discovery boundaries. Add detached decision verification against trusted inputs. |
| Confirmed defect | Literal authority flags accepted integers. Index and precision validation accepted an action ID of 110000 and perpetual `sz_decimals=18`. | Check exact booleans. Introduce the bounded local index and perpetual precision range. |
| Confirmed defect | Catalog order depended on insertion order, and the duplicate-index check excluded stale records. The missing-timestamp reason was unreachable for validated observations. | Canonicalize records, include stale and delisted rows in index uniqueness, and distinguish missing metadata from recorded errors and fixtures. |
| Contract ambiguity | A network-free key allowed the same symbol and DEX on Mainnet and Testnet to share identity. The source label did not bind the exchange-reported coin. | Require the network and exact source coin. Compare against the qualified form derived from validated components. |
| Missing coverage | The 15 original passing tests lacked strict nested construction/copy cases, network separation, serialized ordering, precision and index bounds, and well-formed but mismatched decision digests. | Expand the contract suite to 56 cases and exercise the installed SDK with offline response fixtures. |
| Deferred | Dynamic metadata collection, source endpoint validation, new PAPER profiles, collateral, agents, AMM presets, Market Explorer and rollout gates. | Reserve these for the Phase 18.1–18.7 boundaries in the architecture. |

## Native compatibility evidence

A 40-frame deterministic FLASH_MOVE run used BTC, ETH and SOL with 40,000, 35,000 and 20,000 USDC allocations and a 5,000 USDC reserve. The fixture enabled fees and funding and required nonzero fees and signed funding evidence. An isolated PR #84 checkout and the Phase 18.0B branch produced byte-equivalent canonical result data for the portfolio configuration fingerprint, three native profile and captured configuration fingerprints, dataset and result fingerprints, full native market receipts and the aggregate accounting report. The combined canonical evidence SHA-256 is `12227b4e87303c691a15f820503360fecad8ec39b0d7e31c6004020af5eeba1a`. This check used the existing native fixture builders and execution/aggregation paths.

The isolated SDK 0.24.0 probe supplied local `perpDexs` and `meta` payloads to the SDK's real `Info` mapping. Core BTC, `xyz:BTC` and `test:BTC` each occupied local index 0, while their SDK action IDs were 0, 110000 and 120000. The HIP-3 action IDs failed v2 local index validation. The probe opened no WebSocket and made no provider request.

## Executed checks

| Check | Observed result |
| --- | --- |
| Before editing, `cd backend && python -m pytest -q tests/test_phase180a_market_universe_contracts.py` | **15 passed**, 0 skipped, no warnings reported, 0.29 s. |
| After editing, same focused contract command | **56 passed**, 0 skipped, no warnings reported, 0.39 s. |
| Contract suite with Pydantic 2.10.6 (declared minimum minor release) | **56 passed**, 0 skipped, no warnings reported, 0.60 s. |
| Existing backend regressions | **2,224 passed**, 0 failed or skipped, 2 warnings, 497.40 s. Covers native metadata, market data and streams, simulation, portfolio, guarded execution, Audit 3.0 and Redis fixtures. |
| Full backend, `cd backend && python -m pytest -q -rs --tb=short` | **3,429 passed**, 0 failed or skipped, 2 warnings, 604.69 s. The optional ML coefficient-export test ran. |
| Locked frontend `npm ci`, `npm run typecheck`, `npm test`, `npm run build` | All passed. **789 tests passed**, 0 failed, cancelled, skipped or todo, 17.95 s. Vite built 242 modules in 3.64 s. |
| `npm audit` and `npm audit --omit=dev` | Full-tree audit exited 1 with four high findings along the same development dependency chain (picomatch, fdir, tinyglobby and Vite). Production-only audit passed with zero findings. |

The Python 3.12.14 runs used Linux x86_64. The original baseline used the workspace environment with Pydantic 2.13.5, FastAPI 0.142.2 and Starlette 1.7.0. The hardened and regression runs used an isolated project environment with FastAPI 0.141.1, Starlette 1.6.0, Pydantic 2.13.4, pydantic-core 2.46.4, pytest 8.4.2, pytest-asyncio 0.26.0, Hyperliquid SDK 0.24.0, eth-account 0.13.7, HTTPX 0.28.1, websockets 15.0.1, fakeredis 2.40.0, redis-py 6.4.0, NumPy 2.3.5, scikit-learn 1.8.0 and SciPy 1.17.0. Frontend ran with Node 24.19.0, npm 11.9.0, TypeScript 5.9.3 and Vite 7.3.8.

The default Python lacked pytest and npm's default cache path was unwritable. The workspace Python environment and explicit writable npm cache resolved both setup issues. The first hardened contract run also exposed a strict JSON tuple round-trip issue in the draft catalog pre-validator. The final field uses Pydantic's bounded tuple validation and fail-fast item handling to preserve both wire decoding and catalog bounds. The frontend emitted the existing Zustand storage notice in the test DOM, 12 ignored TanStack Query client directives in the build, and the existing chunk-size warning (largest 728.54 kB). The development advisory is the open Audit 3.0 picomatch 4.0.7 finding. The existing manifests and lockfile were used. [Audit 3.0 final remediation](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md) · [GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf)

Each regression run reported two existing warnings. Starlette TestClient warned about its deprecated HTTPX integration. Pydantic warned while serializing the deliberately malformed concentration selection in `test_phase174_provenance.py::test_resealed_tampering_still_rejected[selection]`. Test counts overlap across commands.

## Readiness

**PASS for Phase 18.1 read-only discovery development.** The v2 contracts passed focused adversarial and full regression checks. Native BTC/ETH/SOL profile, simulation and accounting evidence matched the PR #84 baseline. The Phase 18.1 integration must establish the actual endpoint and network, normalize official metadata and validate its transport and lifecycle before publishing discovery evidence.

Frontend source and selectors required no compatibility changes. Chromium acceptance was outside the Phase 18.0B frontend change gate. Public provider/SDK soak, signed TESTNET operation, physical Redis recovery, platform-specific lifecycle and accessibility, and the other open Audit 3.0 gates retain their recorded scope. The isolated SDK probe and the offline regression suites provide fixture-based evidence. New PAPER eligibility, HIP-3 execution and production execution remain outside this decision.
