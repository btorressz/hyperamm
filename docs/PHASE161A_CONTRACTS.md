# Phase 16.1A — Historical Research Contracts & Provenance

**Scope:** ADD-only foundation. No data importer, database, API route, replay engine, market-data collector, operational risk or signing changes.

## Source identity and authority

Contract version: `phase16-replay-v1`. Each dataset identifies exactly one of BTC/ETH/SOL.

- `RECORDED_NATIVE`: Hyperliquid identity and `USER_ASSERTED_PERMITTED_USE`, with `simulated=false`. This is an importer/user assertion, **not** verified venue authentication or proof of licensing.
- `SYNTHETIC_FIXTURE`: `SYNTHETIC` provider, `SYNTHETIC_GENERATOR` method and `simulated=true`. It cannot claim verified exchange event time.
- `source_authenticated=false`, `licensing_independently_verified=false`, `read_only=true` and `authority=NONE` remain explicit. RedStone/Kraken/CoinGecko historical evidence is never invented.

## Typed contracts

`models.py` adds immutable strict Pydantic types: `HistoricalSource`, `HistoricalBook`, `HistoricalPerpContext`, `HistoricalObservation`, `HistoricalGap`, and `HistoricalDataset`. It reuses existing `Evidence`, `LiveBookLevel`, Decimal wire types and `ResearchPerpMarketId` without changing those components.

A dataset is bounded to 5,000 observations, 1,024 gap declarations and 20 levels per book side; importer **byte/nesting limits** must still be implemented in 16.1B. Sequences strictly increase, receipts do not go backward, observer generations do not regress, and present native L2 source timestamps strictly increase within the same observer generation.

L2 source time may be missing or explicitly unverified. If `source_event_time_verified=true`, an actual L2 source timestamp must be present and the source must be recorded native. Perpetual-context source event time must remain null and unverified, reflecting existing `activeAssetCtx` behavior. Missing economic values stay null; no fabricated market mid, context values or provider history.

Gaps have explicit reason and positive bounded intervals, and do not imply continuous history. `coverage_start/end` are first/last **receipt** times, not a claim of complete exchange coverage. Book snapshots do not establish actual passive fills or queue position.

## Deterministic provenance

`provenance.py` reuses the existing canonical `stable_fingerprint` SHA-256 helper. Dataset fingerprint covers contract, dataset/source identity, ordered observations, gaps and coverage; excludes only its own hash. Component fingerprints cover source, observations and gaps independently. No wall-clock import time, filesystem path, or processing timestamp enters economic identity. Hashes are content identities, **not signatures** or verified source/licensing evidence.

`describe_provenance()` reports observed component counts, verified L2 time count, gap count, and conservative native/synthetic time policy.

## Validation status and future work

The initial author ran 12 focused contract checks in an isolated local Pydantic harness using minimal stand-ins for the inspected repository's existing helpers: **12 passed**. This is **not** a full native HyperAMM regression. Full environment testing, importer security, storage and replay integration are assigned to Codex 16.1B.

For 16.1B, add `research_replay/validation.py`, `importers.py`, and `storage.py`, with bounded secure local-file admission, explicit use authorization, canonical normalization, atomic failure, missing/duplicate/gap checks, replay compatibility and comprehensive adversarial tests. Do not add operational trading authority or auto-fill historical gaps.
