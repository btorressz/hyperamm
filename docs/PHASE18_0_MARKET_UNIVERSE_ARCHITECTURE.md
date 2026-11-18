# HyperAMM Phase 18.0A — Market-Universe Architecture & Contracts

**Status:** additive contracts only; no SDK discovery, new execution, subscriptions, API endpoints or PAPER market enablement.  
**Baseline:** main after PR #84, merge commit `14dfde775c0ce1a3b5517b9db6c9c4fafb48c1de`.  
**Ownership:** ChatGPT 18.0A implementation; Codex 18.0B independent repository and regression acceptance.

## Purpose and trust boundary

HyperAMM's Phase 14–17 research models deliberately limit `ResearchPerpMarketId` to `BTC`, `ETH`, and `SOL`. The existing Hyperliquid TESTNET adapter explicitly rejects non-native asset indices. Phase 18.0A adds a separate read-only, versioned representation for future Core and HIP-3 discovery. It **must not** imply that existing simulation, portfolio, comparison, stream, agents, AMM, Risk Firewall or trading endpoints accept that identity.

Phase 18.0A has zero new network calls, WebSockets, workers, database tables, environment switches, public endpoints, wallet connections, user permissions or signing paths.

## Contract definitions

Source: `backend/app/market_data/market_universe_contracts.py`

- `MarketInstrumentIdentity` holds a `HYPERLIQUID` venue, explicit `CORE_PERP` or `HIP3_PERP` class, `dex` namespace, and **unqualified** instrument name. Core requires empty DEX; HIP-3 requires a nonempty bounded namespace. Symbols and namespaces reject delimiters that would introduce identity ambiguity. The stable key is `venue:class:dex:name`; neither a display label nor a mutable SDK asset index is a canonical identity.
- `MarketUniverseMetadata` keeps observed asset index, size precision, listing state, status, source and UTC observation time. `EXCHANGE_VERIFIED` requires class-matched official metadata, an index, size precision, an explicit listing flag and timestamp. Verified does **not** mean fresh or eligible. DEMO profiles are identified as fixtures, not official evidence.
- `MarketUniverseCatalog` binds an order-independent fingerprint to distinct canonical identities, prohibits duplicate verified indices **within** a class/DEX namespace and has literal `read_only=True` and `authority=NONE`. Reuse of numeric indices across different namespaces is permitted; downstream integrations cannot merge them by index alone.
- `DiscoveryEligibility` records a source metadata fingerprint, evaluation timestamp, eligibility and bounded reason. Its `paper_research_eligible=False`, `execution_eligible=False`, `read_only=True`, and `authority=NONE` fields are literal types; callers cannot grant permissions with serialized data.
- `evaluate_discovery` performs a pure validation and freshness projection with an explicit evaluation time and 1–86,400 second freshness budget. Future timestamps, stale/unavailable evidence, delisted instruments and fixture provenance cannot yield a discoverable result. This is a **read-only discovery signal**, never permission to trade.

Status and freshness are separate: a formerly verified record can age past its configured budget. No metadata source may transform a simulated observation into exchange-verified evidence. Neither a catalog fingerprint nor a discovery decision is a cryptographic identity/authentication of upstream transport.

## Existing code crosswalk (REUSE)

| Existing location | Existing behavior retained | Phase 18 integration constraint |
| --- | --- | --- |
| `app/simulation/market_profiles.py` | BTC/ETH/SOL literal; immutable native research profile; native precision/DEMO anchors | Remains unchanged. Do not import dynamic contracts to widen current research eligibility. |
| `app/market_data/hyperliquid_metadata.py` | Read-only SDK Core metadata single-flight cache, provenance, demo fallback, TTL | 18.1 may adapt existing cache patterns; not its existing three-market authority and not implicit HIP-3 support. |
| `app/market_data/live_models.py`, `live_stream_models.py`, `live_streams.py` | Financial Decimal checks, immutable evidence, bounded read-only observer, lifecycle ownership | Preserve existing contracts and subscriptions. Dynamic observation expansion requires a separate reviewed migration. |
| `app/portfolio_research/models.py` | USDC-only, BTC/ETH/SOL exact capital/allocations, PAPER/none authority, three-market limits | No new markets admitted in 18.0A. Currency/collateral aggregation is 18.3. |
| `app/execution/hyperliquid.py` | Guarded TESTNET, native asset index check `0 <= asset < 10000`, SDK-specific wire/precision normalization | Leave exactly unchanged. HIP-3 discovery must never bypass it. |
| `app/simulation/models.py` | Canonical financial research fingerprint function | Shared for detached metadata and catalog digests; no duplicate hashing engine. |
| Existing AMM, agents, risk, accounting, replay and React terminal | Operational/research behavior supported by PR #84 acceptance | Unmodified; no new authority edges. |

## Design boundaries for subsequent Phase 18 milestones

**18.0B (Codex):** independently validate these models and tests on the latest merged tree, inspect SDK metadata namespace assumptions, run focused and relevant native regressions, challenge collision/freshness/fingerprint behavior, and document any limitations. Fix only demonstrated contract defects, without implementing 18.1.

**18.1 discovery:** load public Core + HIP-3 metadata through existing controlled, read-only SDK/HTTP ownership; validate source classes, bounded cardinality, namespace and stable identity; avoid unbounded subscriptions and ambient permissions. Record verified, stale, unavailable and delisted states. Do not infer listing, asset index or precision from display names. SDK behavior and official API payload formats need independent validation before adding adapters.

**18.2 PAPER:** explicitly decide which discovered markets have validated precision, quantization, DEMO scenarios, fee/funding assumptions, market-specific risk and native simulation support. Add new research eligibility only with strict per-instrument regression and explicit provenance; keep existing BTC/ETH/SOL fingerprints stable.

**18.3 risk:** add separated collateral/quote currencies and exchange-product-specific margin/exposure assumptions before any cross-market aggregation claim; existing USDC-only capital math must not silently apply to every HIP-3 contract.

**18.4 agents:** advisory Market Eligibility, Funding/Basis and Quote Economics agents may consume validated evidence without new trading authority; existing SHADOW/risk supervisor boundaries remain.

**18.5 AMM:** asset-aware research presets and scenario realism require verified market economics and their own invariant checks; not a new trading permission.

**18.6 UI:** React Market Explorer and Starter/Pro/Institutional modes display provenance, eligibility and explicit limitations. Tier names do not change backend authorization.

**18.7 acceptance:** combine independent Core/HIP-3 metadata fixtures, adversarial identity drift and duplicate-index cases, full regression, browser/accessibility, SDK cleanup and explicit no-signing checks. Preserve all unresolved Audit 3.0 external acceptance limits.

## Explicit non-goals

No dynamic market retrieval in 18.0A, no new order book subscriptions, no strategy or portfolio enablement, no HIP-3 TESTNET, no mainnet signer, no operational portfolio reallocation, no agent activation, no auto trading, no remote operator deployment, no code generation and no user-facing trading toggle.

## Exit criteria

1. New versioned contract module and focused tests merged; source references accurate.
2. Reject ambiguous Core/HIP-3 identities, duplicate canonical IDs, namespace-local duplicate indices, invalid or contradictory metadata, future/stale timestamps and attempts to elevate authority.
3. Existing BTC/ETH/SOL types, metadata adapter, stream ownership, guarded execution and accounting are unchanged.
4. Record focused regression, relevant existing backend tests and any limitations accurately; do not claim unexecuted tests passed.
5. Phase 18.1 can implement discovery against the versioned contract without creating hidden permission or evidence upgrades.

## Validation note

This artifact is an architecture/contract handoff. GitHub-based authorship does not itself execute pytest, Chromium, external SDK probes or Redis; independent native execution is a required acceptance gate.
