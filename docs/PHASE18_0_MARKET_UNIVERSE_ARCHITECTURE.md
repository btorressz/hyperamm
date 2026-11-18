# HyperAMM Phase 18.0 market-universe architecture

Phase 18.0 defines immutable, read-only evidence for Hyperliquid Core and HIP-3 perpetuals. PR #85 added isolated identity, metadata, catalog and discovery models plus focused tests on top of Audit 3.0 final remediation. Phase 18.0B reviews merge `115f138` and publishes the hardened `phase180b-v2` contract. Phase 18.1 integrates these contracts with the read-only discovery service, GET route and TypeScript client. [Phase 18.1 acceptance](PHASE18_1_DISCOVERY_ACCEPTANCE.md) · [PR #85](https://github.com/btorressz/hyperamm/pull/85) · [Audit 3.0 final remediation](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md) · [Contract source](../backend/app/market_data/market_universe_contracts.py)

## Identity and exchange metadata

| Field or value | Contract |
| --- | --- |
| `contract_version` | `phase180b-v2` on identities, metadata, catalogs and decisions. |
| `venue`, `network` | `HYPERLIQUID` and an explicit `MAINNET` or `TESTNET`. The collector must establish the network from its configured endpoint. |
| `instrument_type`, `dex`, `instrument_name` | `CORE_PERP` requires the empty DEX namespace. `HIP3_PERP` requires an explicit namespace. The case-sensitive namespace and unqualified instrument name are bounded to 32 and 64 characters respectively. Both nonempty components begin with an ASCII alphanumeric and allow ASCII alphanumerics, periods, underscores and hyphens. These are representation bounds for observed names. Deployment registration has its own venue rules. |
| `stable_key` | `venue:network:class:dex:name`. For example, `HYPERLIQUID:MAINNET:CORE_PERP::BTC` and `HYPERLIQUID:MAINNET:HIP3_PERP:xyz:BTC` are distinct. The key is independent of observation time, source, index and display label. |
| `identity`, `source_coin` | The official row's raw coin must equal the validated identity's derived `exchange_coin`, which is the exact unqualified name for Core and `dex:name` for HIP-3. The collector validates the exact namespace against the requested DEX, preserves case and rejects malformed names or contradictory evidence. |
| `universe_index` | Zero-based ordinal into the unfiltered `meta(dex=…).universe` for the observed network and DEX. The supported range is 0–9,999, which preserves Core's asset-ID range and the HIP-3 offset stride. Enumerate before filtering or sorting and retain delisted entries' ordinals. |
| `sz_decimals` | Integer 0–6 for both perpetual classes, matching the perpetual `6 - szDecimals` fractional price budget and the existing native research bounds. Precision alone grants no research admission. |
| `listed` | Explicit boolean for captured official observations. A returned delisted row has `false`; a missing row has no listing evidence. |
| `observed_at` | Timezone-aware official observation time, normalized to UTC. Freshness is computed relative to a separate supplied evaluation clock. |

The `perpDexs` response starts with a Core placeholder and then lists builder DEXs. A builder DEX's position in that response is its DEX ordinal and its `name` selects the metadata namespace. Core exchange actions use the local index. The documented HIP-3 action ID is `100000 + 10000 × perp_dex_index + universe_index`. The first builder DEX therefore uses action ID 110000 for local index 0. SDK `Info.name_to_asset()` returns the resulting action ID and `Info.meta(dex=…)` supplies the ordered metadata rows. The v2 contract stores only the local ordinal and canonical identity. It exposes neither the exchange action ID nor its derivation. [Asset IDs](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/asset-ids) · [Perpetuals](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals) · [Tick and lot size](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/tick-and-lot-size) · [Python SDK 0.24.0, Info](https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/0.24.0/hyperliquid/info.py)

V2 supersedes the isolated `phase180a-v1` representation. It requires the network, binds the observed coin and replaces the ambiguous `asset_index` with `universe_index`. A v1 payload cannot supply the network or distinguish how its index was obtained. Reconstruct v2 evidence from the source observation. The review found no consumers of v1 outside its tests and documentation. The legacy native `asset_index` and profile versions remain part of their existing contracts.

## Provenance, freshness and validation

| `metadata_status` | Admitted provenance and fields | Discovery outcome |
| --- | --- | --- |
| `EXCHANGE_VERIFIED` | `OFFICIAL_SDK_CORE_META` or `OFFICIAL_SDK_HIP3_META` as selected by the identity class. Requires exact `source_coin`, local index, precision, listing state and observation timestamp. | `NOT_LISTED` for a delisted row. Otherwise `FUTURE_TIMESTAMP` for negative age, `STALE_METADATA` past the supplied freshness budget, or `DISCOVERABLE` within it. The budget boundary is inclusive. |
| `STALE` | The same complete, class-matched observed evidence retained as stale. | `NOT_LISTED`, `FUTURE_TIMESTAMP` or `STALE_METADATA`, in that order. |
| `DEMO_PROFILE` | `PINNED_RESEARCH_FIXTURE`. May carry fixture precision. Exchange coin, ordinal, listing state and observation time must be absent. | `UNVERIFIED_METADATA`. |
| `UNAVAILABLE` | Class-matched official source or `NONE`. No observed coin, ordinal, precision, listing state or timestamp. | `MISSING_METADATA`. |
| `ERROR` | Class-matched official source or `NONE`. No observed coin, ordinal, precision, listing state or timestamp. | `METADATA_ERROR`. |

A catalog contains up to 4,096 records sorted by canonical key. Each key occurs once, and an observed local ordinal occurs once per network, perpetual class and DEX, including retained stale and delisted observations. Constructing, revalidating and fingerprinting a catalog applies those same rules.

The models inherit frozen fields and forbidden extras from `Evidence` and enable strict validation, default validation and recursive Pydantic instance revalidation. Python inputs use native types, including tuples and aware datetimes. JSON validation accepts arrays and aware datetime strings. The record validator stops at the first malformed entry. The discovery transport owns its byte and response limits before decoding. Booleans in literal authority fields are checked explicitly. Catalog admission, fingerprinting, discovery evaluation and detached-decision validation recheck model instances. Pydantic's `model_copy(update=…)` and `model_construct()` create unchecked objects that require validation before use.

Metadata and catalog fingerprints use the existing `stable_fingerprint` canonical serializer on the validated content. They cover provenance, timestamp and network, with equivalent UTC instants normalized and catalog record order fixed. The status describes declared observation provenance and the digest describes content integrity. The Phase 18.1 collector establishes exchange provenance through server-selected official endpoints and namespace validation.

`evaluate_discovery` requires an aware evaluation clock and a whole-second freshness budget of 1–86,400 seconds. A decision binds the canonical identity, metadata fingerprint, UTC evaluation time, discovery result and reason code. The decision's shape verifies the reason/boolean relationship and digest format. To accept a detached decision, `validate_against` recomputes it using independently trusted metadata, evaluation time and budget, then checks the full result.

## Authority and compatibility

Discovery eligibility enables read-only presentation of current observed listings. PAPER research requires an approved profile, precision, economics and engine behavior. Execution requires the separate guarded TESTNET or PAPER execution architecture and final risk authorization. All v2 decisions fix `paper_research_eligible=false`, `execution_eligible=false`, `read_only=true` and `authority=NONE`. Catalogs fix `read_only=true` and `authority=NONE`. The strategy runtime, simulation, portfolio engine, agent supervisor and execution adapter have no consumer of the discovery decision.

| Existing path | Reviewed boundary |
| --- | --- |
| `simulation/market_profiles.py` | BTC/ETH/SOL literal, native precision and fixed DEMO anchors remain the supported research profiles. The dynamic identity stays outside profile and strategy fingerprints. |
| `market_data/hyperliquid_metadata.py` | Core mainnet `Info.meta` loader retains its single-flight, TTL, source-aware native profile and optional DEMO fallback. 18.1 can reuse its lifecycle and refresh patterns. |
| `market_data/live_models.py`, `live_stream_models.py`, `live_streams.py` | Native REST and WebSocket projections share the research market literal. Bounded observer ingress, source ages, provider status and session/sequence identity remain on their native paths. |
| `market_data/hyperliquid.py` | Operational data retains its configured market, own SDK lifecycle, REST recovery barrier and explicit subscriptions. |
| `simulation/models.py`, `portfolio_research/models.py` | Shared canonical hashing is reused. Native profile/configuration/result fingerprints, exactly allocated USDC, modeled fees and funding, ledger and risk evidence retain their existing inputs. |
| `execution/hyperliquid.py` | The existing TESTNET URL and enablement guards, native-only `0 <= asset < 10_000` check, precision normalization and final authorization remain on the established path. The SDK action ID and discovery decision do not cross this boundary. |
| Audit 3.0 | PR #85 added the isolated module, its tests and two documentation changes. PR #84's runtime, liquidity preview, accessibility and Replay changes remain in the baseline. Audit 3.0 fixtures exercise native order precision, stale-context 422, unrepresentable depth, heartbeat handling, modeled PAPER evidence and SHADOW freshness. |

## Frontend compatibility and Phase 18.6 contract

The TypeScript `ResearchMarketId` and `LiveMarketId` are BTC/ETH/SOL. `api/client.ts` uses the existing research, live and portfolio routes. The `ResearchMarketSelector` validates the research catalog, disables selection before admission and surfaces catalog errors with retry. `ResearchMarketDetails` identifies DEMO and official evidence. `LiveMarketSelector` and the Markets workspace use the native observation set, with `liveMarketEvidence.ts` checking identity, transport, metadata and time before rendering. The navigation registry and Markets view keep operational, live and comparison workspaces distinct. The Portfolio Research Terminal binds native configuration and result fingerprints, renders provenance in `PortfolioProvenance`, and gates controls on validated previews and accepted workflow state. `portfolioResearch.ts` validates the compact evidence and `researchMarkets.ts` checks profile availability and provenance. The Phase 18.1 client adds a separate catalog method with runtime validation. Existing selectors continue to use their native market types and endpoints.

The future read-only Market Explorer will use the canonical key for row identity, selection and cache keys, and show a separate display label. The row needs the network, Core/HIP-3 class, DEX namespace, listing state (including unknown and delisted), discovery status and reason, metadata source and status, observation and evaluation times, freshness, PAPER eligibility, execution eligibility and visible limitations. Validate the contract version, identity, provenance and freshness together before displaying an eligible state. Retire stale or unsupported selections and surface loading, unavailable, stale and invalid evidence through accessible status and disabled-state patterns. Discovery results stay separate from native research and operational selectors. Starter/Pro/Institutional presentation modes leave eligibility and authorization with the backend.

## Next milestones

| Phase | Scope |
| --- | --- |
| 18.1 | Dynamic read-only Core and HIP-3 metadata collection. Validate endpoint/network, DEX inventory and requested namespace, names, delisting semantics, precision, metadata volume and SDK cleanup before publishing a catalog. Test public provider and failure behavior in the integration. |
| 18.2 | Generalize profiles, precision, modeled economics and explicit PAPER eligibility with per-instrument acceptance. |
| 18.3 | Model market-specific collateral, exposure and risk before aggregating across differing products or currencies. |
| 18.4 | Evaluate Market Eligibility, Funding/Basis and Quote Economics advisory agents within existing authority boundaries. |
| 18.5 | Add asset-aware AMM research presets and validate execution realism. |
| 18.6 | Build Market Explorer and Starter/Pro/Institutional UI with accessible provenance and eligibility states. |
| 18.7 | Run comprehensive multi-market regressions, provider and browser acceptance, and explicit final rollout gates. |

[Phase 18.0B acceptance evidence](PHASE18_0B_ACCEPTANCE.md)
