# Phase 18.6H hardening acceptance

Phase 18.6H starts at the PR #99 merge, `1b9804146a8de82e7432e18493591385b0f4bb0c`. Phase 18.6A introduced Core and HIP-3 listing metadata and a qualified PAPER handoff. Phase 18.6H adds public market observations. [PR #99](https://github.com/btorressz/hyperamm/pull/99) · [18.6A–E acceptance](PHASE18_6_IMPLEMENTATION_ACCEPTANCE.md)

## Implementation inventory

| Target | Reuse, enhancement and addition |
| --- | --- |
| Reuse 50% | Official public SDK transport, network allowlist, bounded parsing and session closure, catalog generations, canonical market identity, exact Decimal validation, and the discovery and PAPER handoff. The existing React Query client, display store, navigation, panels, 13 routes and nine agents provide the workspace foundation. |
| Enhance 35% | `market_universe_discovery.py` and `advisory_market_observations.py` share the DEX-scoped public context operation. `api/market_universe.py` and `main.py` expose and own summaries. `MarketExplorer.tsx`, `ExperienceModeSwitch.tsx`, `api/client.ts` and `phase186.css` present observations and the selector. `App.tsx`, `Dashboard.tsx`, `PortfolioResearch.tsx`, `Simulation.tsx` and `GeneralizedPaper.tsx` compose the existing workspaces. `format.ts` shares decimal comparison with `marketRisk.ts`. |
| Add 15% | `market_summaries.py` contains the owner and versioned contract. `marketSummaries.ts`, `useMarketSummaries.ts` and `ObservedMarketSummary.tsx` validate, expire and present the same evidence. Focused backend and frontend suites, the existing Phase 18.2 and 18.6 browser harnesses and legacy Vault navigation assertion, the Phase 18.6H captures, this report, and the updated implementation acceptance, roadmap and changelog record the changes. |

## Contract and source binding

`POST /api/v1/market-universe/market-summaries` accepts 1–13 unique canonical keys, an expected catalog fingerprint, the catalog network and an optional manual-refresh flag. `phase186h-v1` returns one row per key in request order, with canonical identity, ordinal, metadata fingerprint, a separate observation fingerprint for successful captures, the public source, server evaluation and receipt times, expiry, numerical strings or nulls, units, and bounded limitations. All responses carrying summaries declare read-only, execution eligibility false and authority `NONE`. The existing metadata route retains its metadata-only contract.

Each acquisition verifies the returned namespace universe against active discovery in original order. It checks every listing’s identity, source coin, ordinal, size precision and listed status. Named context rows must agree with the canonical coin, network and DEX when those fields are supplied. A changed universe, shortened positional array or conflicting denomination cannot attach market values. A null row preserves positional binding and leaves its fields unavailable. The server rechecks the generation immediately before publication. A retired generation receives HTTP 409, and a key absent from the active catalog receives 404.

## Financial and timestamp semantics

- Mark and oracle come from `markPx` and `oraclePx`. Prices use provider quote per base, volume uses provider notional quote, and open interest uses base units. A matching discovery collateral index confirms metadata consistency. The API leaves quote denomination unverified. Mark/oracle basis stays unavailable where compatible denominations cannot be established.
- `funding` is the current hourly rate, represented as a decimal fraction with a 3,600-second interval. The display converts it to percent per hour. Hyperliquid documents a maximum absolute rate of 0.5% per hour. Cash flows and annualized returns require other evidence. [Hyperliquid funding specification](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding)
- The mark comparison is `(markPx - prevDayPx) / prevDayPx × 100` in the same market context. The server uses bounded Decimal arithmetic and rounds to eight decimal places. It compares against the provider’s previous-day reference. Both prices must be valid and positive. Negative notional or open interest, invalid or nonfinite numbers, binary floats and unsupported funding rates leave the affected fields unavailable. A reported zero is preserved for volume, interest or funding.
- `metaAndAssetCtxs` provides no documented event timestamp for these fields. `provider_event_at` is null and `LOCAL_RECEIPT` labels server receipt after the bounded read. The cache uses a separate monotonic storage timestamp. Client expiry is checked against the server deadline and a monotonic lifetime measured from request start. The Explorer hides expired values and shows stale status.

## Batching and failure states

The summary owner acquires `metaAndAssetCtxs` through the existing public HTTP transport using POST to `https://api.hyperliquid.xyz/info` on Mainnet or `https://api.hyperliquid-testnet.xyz/info` on Testnet. Core uses an empty DEX parameter. HIP-3 uses the selected named DEX. The pinned SDK 0.24 method omits the DEX argument, so discovery and advisory share an explicit scoped payload through the existing SDK session transport. Summary requests use the context operation alone. Discovery still supplies catalog metadata and collateral binding. [Official perpetual Info operations](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals) · [Info identity semantics](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint) · [SDK](https://github.com/hyperliquid-dex/hyperliquid-python-sdk)

| Limit | Behavior |
| --- | --- |
| Namespace requests | Up to three active acquisitions across the owner. Concurrent readers share one task per generation and DEX. A cold 12-market page in one namespace uses one provider call. Mixed pages can return a partial result, with older or missing captures prioritized on the next refresh. |
| Retention | At most 24 cached namespace captures, 15-second reuse window, and a five-second minimum before issuing another manual request for the same cached namespace. Current evidence expires after at most 30 seconds or at catalog expiry. The Explorer refreshes every 20 seconds while visible. |
| Request budgets | At most 24 acquisitions per rolling minute, or 480 documented IP weight per minute for this owner. The public HTTP reader caps the body at 1 MiB. Thirteen bounded normalized rows fit the 32 KiB browser response budget. Provider wait has a six-second request budget, and HTTP 429 triggers 30 seconds of owner backoff. [Hyperliquid limits](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits) |
| Failure and shutdown | Capacity, provider timeout, rate limit, invalid data, stale, unsupported and missing observations have structured states. A cancelled browser or disconnected HTTP request releases its waiter. Shared bounded work may finish for another caller and always closes its SDK session. Lifespan shutdown drains acquisitions and clears the cache. |

## Public provider evidence

An independent check used the official SDK transport, the real discovery owner, and the new HTTP route through FastAPI’s ASGI transport. Mainnet discovery returned HTTP 200 with 11 namespaces. The summary returned HTTP 200 with two valid, separately bound rows. These are point-in-time provider values, in as-reported units.

| Market | Server receipt (UTC, 2026-11-20) | Mark | Oracle | Hourly funding fraction | 24h notional | Open interest, base | Previous-day reference |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Mainnet Core BTC | 13:15:38.926466 | 61544.0 | 61578.5 | −0.000006833 | 5301822541.9807357788 | 39907.55694 | 63753.0 |
| Mainnet HIP-3 `xyz:XYZ100` | 13:15:39.059953 | 26036.0 | 26020.0 | 0.0000335104 | 803970408.4187999964 | 14349.5782 | 27710.0 |

Separate public probes returned matching metadata and context arrays of 235 Core rows and 147 `xyz` rows on Mainnet, and 213 Core rows on Testnet. The Testnet Core probe returned SOL mark 70.388, funding −0.0005627017, notional 274343.46517 and open interest 6721.28. Testnet discovery returned 503 because its 287 inventory entries exceed the existing 64-namespace limit. The new route retains this admission boundary. Fixture tests verify working Testnet binding inside that limit. Market Explorer needs a current discovery catalog with `MARKET_UNIVERSE_ENABLED=true`. It uses the network configured in `MARKET_UNIVERSE_NETWORK`.

## Experience modes and compatibility

Explorer retains symbol and DEX search, class, listing, metadata and eligibility filters, pagination and the canonical research handoff. Cards show status, age and field-level availability. Detail shows oracle and previous-day values, units, receipt, metadata and observation fingerprints. Financial sorting covers current observations on the visible page in provider units.

Starter retains guided eligibility, both advisory summaries and user-entered synthetic prices. Qualified selected-market observations use a separate request and display. Pro adds a research overview above the existing operator dashboard with operational and research selections, current AMM controls, six distinct supervisory states and links to the three PAPER advisories, Replay and comparisons. Institutional adds configuration, modeled risk and exposure, provenance and operational workspaces over the existing BTC/ETH/SOL portfolio evidence. Segmented buttons persist the existing display preference. They leave the active route, history and in-flight PAPER session under their existing owners.

## Verification

| Check | Executed evidence |
| --- | --- |
| Focused backend | 249 tests passed across the summary route, discovery, Advisory API and Phase 18.5A–F. Within that set, 30 summary tests covered the 12:1 cold acquisition ratio, cache reuse, mixed-page rotation, identity and quote conflicts, numerical rejection, rate limits, deadlines, cancellation and shutdown. |
| Frontend | Locked `npm ci`, `npm run typecheck`, `npm test` and `npm run build` passed. 949 tests passed, with zero failures, skips or cancellations. Vite retained the existing TanStack directive and bundle-size warnings. |
| Phase 18.6H Chromium | Eight workflows passed in Chrome 151.0.7922.173, with 35 checks across 390, 768, 1024, 1440 and 1920 px, and a 200% browser zoom check. The measured 720 px viewport matched document width at 200%. Keyboard and mobile navigation, stale and late response retirement, pagination, and one real PAPER run across all three modes passed. |
| Legacy Chromium | 36 Generalized PAPER, risk, advisory and asset-aware checks; 13 Live Markets; 15 Market vs Research; 16 Historical Replay; 14 Portfolio; 22 Scenario vs Historical. The older asset panel scan reported one item for manual review and zero automated violations. |
| Scoped accessibility | Fourteen axe A/AA scans reported zero automated violations and zero incomplete findings. Manual review covered the captured layout and visible labels. It did not cover screen readers, alternate browsers, or OS accessibility settings. |
| Authority | The summary test instrumented signed exchange operations, cancel and leverage changes, key derivation, signing, the operational adapter, supervisory evaluation, the Firewall and final quote authorization. Zero calls reached those paths. The browser’s recorded POSTs were confined to read-only summaries and existing local PAPER and advisory operations. |

The browser screenshots use the local DEMO terminal and deterministic context fixtures with a visible **DEMO · PROVIDER FIXTURE** label. The screenshots show fixture BTC mark 65,012.5 and fixture `xyz:GOLD` mark 2,405.25. PAPER outcomes come from the existing local worker. The public provider evidence above comes from separate requests. [Chromium measurements](acceptance/phase186h/browser-results.json) · [Desktop Explorer](acceptance/phase186h/market-explorer-1440.png) · [Missing observations](acceptance/phase186h/market-explorer-missing-1440.png) · [Mobile Explorer cards](acceptance/phase186h/market-explorer-cards-390.png) · [Starter](acceptance/phase186h/starter-1440.png) · [Pro desktop](acceptance/phase186h/pro-1440.png) · [Pro mobile](acceptance/phase186h/pro-390.png) · [Institutional desktop](acceptance/phase186h/institutional-1440.png) · [Institutional mobile](acceptance/phase186h/institutional-390.png) · [Supervisory agents](acceptance/phase186h/agents-1440.png) · [Advanced PAPER](acceptance/phase186h/simulation-advanced-1440.png)

The fixed-clock compatibility probe compared complete serialized admission and result pairs with PR #99. It ran Core DOGE and HIP-3 `xyz:GOLD` for 40 frames, with 7/13 bps fees and two-second funding. Standard mode covered all 13 scenarios and three scenarios under each modeled risk mode per market. Asset-aware cases covered the same three scenarios in all three risk settings, using Constant Product for DOGE and Concentrated Liquidity for GOLD. The pairs matched byte for byte.

| Capture | Count | SHA-256 on both trees |
| --- | ---: | --- |
| Standard PAPER | 38 | `b564ad46f264f8b8295feb5dc59d4c44a3e97b2302769663aaf94dbd5fbce65e` |
| Asset-aware PAPER | 18 | `5fa22910e35da8655a6f99df148cc809a2d6043ba090c2ae051ba479e64cf47f` |

The Phase 11 Vault source assertion failed on the original PR #99 tree because it targeted the former flat sidebar. It now checks the existing grouped route links, canonical fallback and active-page labeling. The browser also verified Vault remains reachable.

To reproduce browser acceptance, run `python frontend/tests/browser-phase186.py --python /path/to/backend-python --axe /path/to/axe.min.js --output work/phase186h-browser` from the repository root.

## Phase 18.7 gates

Phase 18.7 retains independent cross-market and cross-browser validation, assistive technology review, provider soak and rollout acceptance. Testnet catalog-cap policy, operational signing and reconciliation, recovery and wider-market release controls remain separately gated.
