# Phase 18.6A–E implementation acceptance

Phase 18.6 starts from `main` at `8b0e77d`, merged PR #98. The baseline includes read-only Core and HIP-3 discovery, source-bound Generalized PAPER, collateral and margin research, three observational advisories, and asset-aware PAPER with both AMMs. [PR #98](https://github.com/btorressz/hyperamm/pull/98) · [Phase 18.5](PHASE18_5_FINAL_ACCEPTANCE.md) · [Phase 18.4](PHASE18_4_FINAL_ACCEPTANCE.md)

| Milestone | Implementation |
| --- | --- |
| 18.6A Market Explorer | Default Markets view, search by symbol or namespace, Core/HIP-3, listing, metadata and research filters, 12 results per page, current evidence details and qualified research handoff. |
| 18.6B Starter | Four guided steps use the existing discovery, scenario catalog, PAPER admission, worker and results. Advanced controls are available on demand. |
| 18.6C Pro | Groups strategy and AMM configuration, the six supervisory agents, Generalized PAPER and the three advisories, Historical Replay and research comparisons. |
| 18.6D Institutional | Portfolio overview with existing configuration, stress, analytics and provenance. Links connect operational risk, execution, Vault accounting, audit logs and historical comparison. |
| 18.6E Integration | One route registry, browser-local mode preference, additive workspace links, responsive layouts and keyboard navigation. |

## File inventory

| Change | Files and responsibility |
| --- | --- |
| Reuse | `api/client.ts` and all Python APIs, native `ResearchMarketSelector.tsx`, `LiveMarketsView.tsx`, `TerminalPrimitives.tsx`, `useMobileNavigation.ts`, `AgentPanel.tsx`, risk and asset research panels, replay and comparison components, and `usePortfolioResearch.ts` with its portfolio components. |
| Enhance | `Markets.tsx`, `researchMarkets.ts` and `marketUniverse.ts` share validated discovery and bind the research handoff. |
| Enhance | `Simulation.tsx`, `GeneralizedPaper.tsx`, `GeneralizedPaperAdvisory.tsx`, and the Generalized PAPER types and validator share the guided and advanced flow and validate the optional simulated Risk Firewall counts before rendering. |
| Enhance | `Agents.tsx` links the existing supervisory page to the research advisories. `PortfolioResearch.tsx` organizes the existing institutional evidence entry points. |
| Enhance | `App.tsx`, `Sidebar.tsx`, `Header.tsx`, `usePageNavigation.ts`, `display.ts` and `navigation.ts` compose one application and retain existing navigation and mobile drawer behavior. |
| Add | `MarketExplorer.tsx`, `GuidedPaperResearch.tsx`, `ExperienceModeSwitch.tsx` and `phase186.css`. |

## Discovery, research and evidence

- Explorer reads the current `/api/v1/market-universe` response. The API supplies bounded listing metadata and DEX inventory. The UI uses the catalog freshness window and displays stale, unsupported and unavailable states. Listing metadata supplies size precision and provenance. Market prices and funding are unavailable in this catalog.
- The handoff binds the network, DEX, instrument type and instrument name via the canonical market key, plus the catalog and metadata fingerprints. The receiving workspace revalidates the handoff. The operational market and the separate native BTC/ETH/SOL research selector retain their own state.
- Starter offers a small selection from the server scenario catalog, a user-supplied synthetic reference price, explicit eligibility and run actions, and a results view. The result uses the validated PAPER vault's P&L, fees, funding and inventory, with modeled Risk Firewall counts when supplied. Existing Market Eligibility and Quote Economics panels use their original evidence and receipt flow. Missing margin or quote evidence stays explicit. P&L and modeled quote economics describe the scenario.
- The single Generalized PAPER request owner persists across mode, tabs and in-app navigation. Mode changes preserve its proposal, admission, completed result and in-flight request. Discovery generation and expiry, market and proposal edits, risk and asset model changes, and advisory freshness keep their validity checks. A browser fetch cancellation leaves an already admitted worker under server ownership.
- The six operational agents remain in Supervisory Agents. Market Eligibility, Funding/Basis and Quote Economics remain observational in PAPER research, with their own source, confidence and unsupported states. Both AMM models remain available in existing configuration, and asset-aware PAPER uses the existing policy and admission flow.
- Institutional Portfolio Research is scoped to its supported native BTC/ETH/SOL contracts. Validated hypothetical allocations, native accounting, stress and provenance retain their original meanings. Operational risk and Vault evidence remain in their existing workspaces. Cross-DEX capital, combined HIP-3 equity, verified custody and production certifications are outside the available evidence.

## Routes and presentation

The 13 legacy routes remain available in all modes. Their hashes are `#/dashboard`, `#/markets`, `#/strategy`, `#/amm-settings`, `#/execution`, `#/risk`, `#/agents`, `#/vault`, `#/analytics`, `#/simulation`, `#/portfolio-research`, `#/logs` and `#/settings`. Additive links provide Starter Home, PAPER, Results, Replay and both comparison views. The previous advanced experience is the default Pro presentation. A mode change saves a display preference in the existing browser storage and keeps the current route. Header controls and status retain their original operational authority.

## Verification

| Check | Result |
| --- | --- |
| Locked frontend install, typecheck, unit tests and production build | Passed. 923 tests. Vite retained its bundle-size notice. |
| Browser experience suite | Seven workflows passed. It covered a 2,006-record catalog, catalog expiry and changes, a real guided run across mode changes, and the Pro and Institutional links. |
| Responsive layout | Five widths per workspace across Explorer, Starter, Pro, Institutional and Advanced Simulation, totaling 25 checks. Chromium 200% zoom reflowed the 1,440 px window to 720 CSS px. No document-level overflow in the measured views. |
| Experience accessibility | Ten scoped axe WCAG A/AA scans reported zero violations and zero incomplete findings. Keyboard mode selection, drawer escape and focus restoration, Results focus, form labels and live statuses were exercised. |
| Historical Replay, Scenario vs Historical and Portfolio Chromium | 16 Replay, 29 Scenario vs Historical and 22 Portfolio workflows passed. |
| Backend compatibility | 122 Phase 18.5 tests passed against the existing backend. The production diff is frontend-only. |
| Generalized, risk, advisory and asset-aware PAPER Chromium | 36 checks passed, including stale, expired, rejected and failed evidence, network replacement, both AMM models and scoped axe A/AA checks. |
| Live Market Intelligence and Market vs Research Chromium | 13 live-market and 15 market-comparison workflows passed, including navigation between the existing views. |
| All-route Chromium accessibility | The Audit 3 harness passed 32 route and viewport measurements with zero automated violations, including all 13 legacy routes at desktop and mobile. It also passed keyboard scroll, focus, sampled contrast and the separate 200% zoom check. Axe requested manual contrast review for the brand mark, navigation and order-book cells. The harness measured at least 6.71:1 in the samples it covers. |

Run the new harness with `python frontend/tests/browser-phase186.py --python /path/to/backend-python --axe /path/to/axe.min.js --output work/phase186-browser`. It uses the existing Phase 18.2 fixture app and launch pattern. [Browser measurements](acceptance/phase186/browser-results.json)

| Screenshot | Desktop | Mobile |
| --- | --- | --- |
| Market Explorer | [1,440 px](acceptance/phase186/market-explorer-1440.png) | [390 px](acceptance/phase186/market-explorer-390.png) |
| Starter guided PAPER | [1,440 px](acceptance/phase186/starter-1440.png) | [390 px](acceptance/phase186/starter-390.png) |
| Pro AMM Settings | [1,440 px](acceptance/phase186/pro-1440.png) | [390 px](acceptance/phase186/pro-390.png) |
| Institutional Portfolio Research | [1,440 px](acceptance/phase186/institutional-1440.png) | [390 px](acceptance/phase186/institutional-390.png) |
| Advanced Simulation | [1,440 px](acceptance/phase186/simulation-advanced-1440.png) | [390 px](acceptance/phase186/simulation-advanced-390.png) |
| Supervisory Agents | [1,440 px](acceptance/phase186/agents-1440.png) | |

## Completion decision

Phase 18.6A–E is implementation-complete and passes the scoped local regression and browser acceptance above. Draft PR #99 stays open for review. [Draft PR #99](https://github.com/btorressz/hyperamm/pull/99)

## Phase 18.7 handoff

Phase 18.7 owns independent rollout acceptance across provider networks and representative Core/HIP-3 cohorts, target browser and operating-system combinations, and release readiness. Production signing, HIP-3 execution and venue permission changes are outside Phase 18.6. Browser captures use the local DEMO terminal and deterministic discovery fixtures. PAPER calculations in the browser harness come from the real local worker.
