# Phase 18.1 market discovery acceptance

Phase 18.1 adds opt-in, read-only discovery for Hyperliquid Core and HIP-3 perpetuals. The implementation is based on `main` at `ac1bfcf` (PR #86). The repository review covered PR #84's Audit 3.0 remediation, PR #85's initial market-universe contracts, PR #86's hardening, and the native metadata, observation, execution and research boundaries. [Audit 3.0](../AUDIT_REPORT_3.0.md) · [Audit 3.0 acceptance](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md) · [Phase 18.0B acceptance](PHASE18_0B_ACCEPTANCE.md)

## Scope and files

| Work | Implementation |
| --- | --- |
| Reuse | `phase180b-v2` identities, metadata, catalog canonicalization, fingerprints and `evaluate_discovery`. The service follows the native metadata cache's single-flight pattern and reuses live-observation error classification. |
| Enhance | `backend/app/config.py` and `backend/app/main.py` configure and own discovery. The new router shares the existing API prefix and application lifespan. `frontend/src/api/client.ts` reuses the bounded JSON reader. |
| Add | `backend/app/market_data/market_universe_discovery.py` collects, normalizes and caches metadata. `backend/app/api/market_universe.py` publishes the catalog. `frontend/src/types/marketUniverse.ts` and `frontend/src/utils/marketUniverse.ts` validate typed wire evidence. |
| Acceptance | Two `backend/tests/test_phase181_*.py` modules, `frontend/tests/phase181-market-universe.test.cjs` and its runner registration. The changelog and Phase 18.0 architecture record the new integration. |

The operational runtime, native research and live market routes, selectors, six native streams, Risk Firewall, PAPER/SHADOW separation, accounting, AMM, agents and guarded TESTNET adapter retain their existing entry points. Discovery serves evidence through its own GET route and the optional TypeScript client method. The route and every discovery decision fix `read_only=true`, `authority=NONE`, `paper_research_eligible=false` and `execution_eligible=false`.

## Sources and normalization

Set `MARKET_UNIVERSE_ENABLED=true` to enable discovery. `MARKET_UNIVERSE_NETWORK` accepts `MAINNET` (default) or `TESTNET`. Each maps to its exact official SDK endpoint. The GET route uses server configuration for the network and provider target.

The collector uses SDK 0.24.0 `Info.perp_dexs()` to fetch public `/info` type `perpDexs`. It validates the Core placeholder and builder namespace entries, then calls `Info.meta(dex=…)` for Core and every admitted namespace. The collector supplies empty constructor metadata and `skip_ws=True` so initialization avoids auxiliary provider calls. The SDK supplies the request payloads. A bounded HTTP adapter uses the official HTTPS endpoint, blocks redirects and buffers up to 1 MiB of identity-encoded UTF-8 JSON per response. Duplicate JSON fields, excessive nesting and malformed responses fail closed. Request sessions carry public metadata calls and close after each call, including failed initialization when a session was created. [Hyperliquid Info endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint) · [Perpetual metadata](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals) · [SDK 0.24.0 Info](https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/0.24.0/hyperliquid/info.py)

Canonical keys bind the venue, network, perpetual class, case-sensitive DEX namespace and unqualified name. Core requires the empty namespace and an exact unqualified source coin. HIP-3 requires the requested namespace and an exact `dex:name` source coin. The provider array supplies the zero-based local ordinal before catalog sorting. The catalog includes delisted rows and preserves indices. The official wire flag `isDelisted` is optional. Omission represents a listed row in a valid universe and a present flag must be a boolean. Empty or missing universes fail with `MISSING_METADATA`. Class, namespace, network and index echoes, when present, must agree with the request and ordinal. Size precision requires a strict integer from 0 to 6. [Asset IDs](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/asset-ids) · [Tick and lot size](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/tick-and-lot-size)

The service admits up to 64 namespaces including Core and up to 4,096 records in a full catalog. An overflow invalidates the attempted generation with `CATALOG_CAPACITY`. The v2 model rejects duplicate identities and repeated ordinals within a network, class and namespace. Ordinals can repeat across namespaces. Fingerprints cover the canonical content including observation times and metadata status. A reordered inventory with the same normalized evidence yields the same catalog fingerprint. Exchange action IDs and spot metadata stay outside the response.

## Refresh ownership and failure states

A GET starts a refresh when the cache expires. At most one generation runs per application instance, with up to three concurrent SDK requests. Requests use five-second connect/read timeouts bounded by the remaining generation budget. Waiting readers receive a timeout after the 15-second generation deadline. A late generation cannot publish. The service retains ownership of any remaining SDK workers until they drain. Request cancellation leaves the shared refresh running. Lifespan shutdown prevents new requests and waits for outstanding workers and session cleanup. Refresh is demand-driven.

The 60-second TTL starts when a generation begins. The API reevaluates every retained record using the current UTC evaluation timestamp and the 60-second freshness budget. A verified generation with an expired or future observation is projected as stale. The existing reason precedence preserves `NOT_LISTED` on delisted records. A failed attempt uses exponential backoff from 5 to 60 seconds, with a minimum of 30 seconds for a rate limit. A success resets the backoff.

A complete generation publishes atomically. If Core refreshes and any builder namespace fails, the response is `PARTIAL`. Inventory, Core or aggregate-capacity failures produce `UNAVAILABLE`. Both states expose the last complete catalog with every record marked `STALE` when a prior catalog exists. They return a null catalog otherwise. Current-attempt namespace diagnostics distinguish fetched, failed and skipped targets, along with bounded reasons such as `NETWORK_MISMATCH`, `NAMESPACE_CONFLICT`, `UNSUPPORTED_METADATA` and `CLEANUP_ERROR`. Successful namespace checks in a failed attempt describe that attempt's observation time. Every retained catalog record and decision belongs to the prior generation.

## API and TypeScript

`GET /api/v1/market-universe` serves the `phase181-v1` envelope around the v2 models. It includes the configured network, canonical record array, catalog fingerprint, aligned eligibility decisions with metadata fingerprints, collection and evaluation times, refresh status and limitations. No-store applies to every route response.

| HTTP | Availability |
| --- | --- |
| 200 | `AVAILABLE`, `PARTIAL` or `STALE` with typed evidence |
| 429 | `UNAVAILABLE` with rate-limited collection and `Retry-After: 30` |
| 504 | `UNAVAILABLE` with timeout when rate limiting did not take precedence |
| 503 | `DISABLED` or other `UNAVAILABLE` causes |

`api.marketUniverse(signal)` validates before resolving, including structured unavailable responses. It checks the schema and contract versions, authority flags, network, namespace and source bindings, canonical order, local indices, observation times, eligibility reasons and HTTP status agreement. The client bounds the response to five million bytes. The maximum-length record fixture with 4,096 records fits that budget. Existing native client methods and market selection use their established contracts.

## Executed checks

| Check | Result |
| --- | --- |
| Final focused backend discovery and API tests | **93 passed**, 0 failed or skipped, one warning, 2.22 s. |
| Existing targeted backend regressions | **927 passed**, 0 failed or skipped, one warning, 71.31 s. Native profiles/metadata, live observations and streams, v2 contracts, strategy feasibility and PAPER simulation, portfolio accounting/risk, execution guards and Audit 3.0. |
| Full backend `python -m pytest -q -rs --tb=short` | **3,522 passed**, 0 failed or skipped, two existing warnings, 604.09 s. The optional ML coefficient-export test ran. |
| Focused frontend contract and API client | **25 passed**, 0 failed, cancelled or skipped. |
| Locked frontend `npm ci`, typecheck, tests and production build | **Passed** with a writable npm cache. **814 tests passed**, 0 failed, cancelled, skipped or todo. Vite built 243 modules in 2.59 s. The existing directive, storage and bundle-size notices were observed. |

Backend checks used Linux and Python 3.12.14 with FastAPI 0.142.2, Starlette 1.7.0, Pydantic 2.13.5, SDK 0.24.0, Redis client 6.4.0 and scikit-learn 1.8.0. Frontend checks used Node 24.19.0, npm 11.9.0, TypeScript 5.9.3 and the existing lockfile. The backend warnings are Starlette's TestClient HTTPX deprecation and the existing Pydantic serialization warning in the deliberately malformed concentration-selection test.

## Native financial compatibility

Ran the existing 40-frame `FLASH_MOVE` fixture with fees and funding enabled, including 40,000, 35,000 and 20,000 USDC allocated to BTC, ETH and SOL and 5,000 USDC retained. Compared an isolated checkout of `ac1bfcf` to the Phase 18.1 tree. Native profile and strategy fingerprints, captured configurations, dataset and result fingerprints, full PAPER receipts, AMM swap outputs, aggregate accounting, exposure and risk evidence matched byte for byte. The SHA-256 of this expanded canonical evidence projection is `96c320fc3fe941a031e3472fe881f83e10298af3b68e82a6346e570196d53d61`. [Native fee and funding fixture](../backend/tests/test_phase173_accounting.py)

BTC and ETH produced fees of 0.235668631 and 0.942527978 USDC and funding of −0.00047649500 and −0.00191180880 USDC respectively. SOL had zero fees and funding in this run. Native financial source paths and existing React workspaces were verified against `ac1bfcf`.

## Official provider check

A bounded live check on November 18, 2026 at 3:24 p.m. Pacific exercised the real SDK transport. Mainnet returned **566 normalized records** (235 Core and 331 HIP-3 across 10 namespaces), including `xyz` (146) and `para` (40). At evaluation, 352 records were discoverable. All records and decisions validated against v2, including the network, source, canonical fingerprint and authority flags. The TypeScript validator accepted the serialized result.

Testnet advertised **285 builder DEXs**, so the full catalog returned `UNAVAILABLE` with `CATALOG_CAPACITY`. Separate bounded Testnet `meta` calls normalized 213 Core records, one `test` record and two `unit` records. The TypeScript validator accepted the Testnet unavailable envelope. All 16 public requests used the selected official endpoint and all 16 SDK sessions closed. Discovery worker threads were drained. The GitBook documentation URLs were blocked by the environment proxy. SDK 0.24.0 source, the preceding architecture record and the official provider responses supplied the wire evidence.

## Readiness and open gates

**PASS** for bounded Mainnet discovery, with network isolation and Testnet failure handling verified by fixtures and public requests. The accepted discovery surface supports Phase 18.2 development of generalized profiles, precision handling and explicit PAPER research admission.

Testnet-wide collection is outside the current inventory bound. A separate inventory inspection found one Testnet namespace outside the v2 name grammar. Sustained provider soak and broader lifecycle platform coverage remain open. The existing picomatch dev-tool advisory, signed TESTNET acceptance, physical Redis and durable recovery gates, authenticated historical data, provider-specific and accessibility limits retain their Audit 3.0 and Phase 18.0B dispositions. Frontend acceptance covers the API client and existing workflows because the frontend changes are confined to API compatibility. [Audit 3.0 unresolved gates](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md#remaining-limits-and-verdict) · [Phase 18.0B readiness](PHASE18_0B_ACCEPTANCE.md#readiness)
