# Phase 16.1B — Historical Import Validation, Storage & Adversarial Acceptance

Base: `main` at `7001e070b7094c5fdcde055e3240cfb73c089a6b`, merged PR #56.
Scope is additive: three isolated research modules, their native acceptance tests,
and this document. The 16.1A models/provenance and Phase 1–15.5 production files
are unchanged. There is no replay engine, frontend, API route, collector, live
subscription, strategy/risk/signing/execution/accounting change or worker startup.

## Admission and use

```python
from pathlib import Path
from app.research_replay.importers import ImportAssertions, import_file
from app.research_replay.storage import HistoricalStorage

dataset = import_file(
    Path("/trusted/imports"), "capture.json",
    assertions=ImportAssertions(
        market="BTC-PERP", source_id="recording:btc-v1",
        source_kind="RECORDED_NATIVE", permitted_use=True,
    ),
)
# Provision this private directory explicitly; the library does not create it.
vault = HistoricalStorage(Path("/trusted/private-history"))
stored = vault.save(dataset)
assert vault.read(stored.dataset_id) == stored
```

`ImportAssertions` is a separate, strict caller assertion, revalidated even when
constructed with unsafe model-copy helpers. Market, source ID and native/synthetic
kind must match the file. Caller markets are BTC-PERP/ETH-PERP/SOL-PERP; wire
markets remain BTC/ETH/SOL, preserving `phase16-replay-v1`. Synthetic sources retain
their synthetic labels and cannot be promoted into recorded evidence. A false
permission assertion prevents reading. The source's own use-attestation must also
satisfy the original contract.

Neither these assertions nor a fingerprint authenticate Hyperliquid or establish
licensing. `source_authenticated=false`, `licensing_independently_verified=false`,
`read_only=true` and `authority=NONE` remain enforced. The optional original-dataset
fingerprint is a supplied lineage assertion, not an independently verified source.

Only one UTF-8 JSON object with explicit `contract_version` is admitted. Unknown
fields, duplicate keys at every depth, trailing documents, malformed encodings,
surrogates, nonfinite numbers, JSON floats, excessive integers and compressed or
executable inputs fail closed. Financial decimals use existing bounded wire types;
decimal strings are preferred. No archive is opened or expanded, even when its
filename ends in `.json`. No pickle, YAML, shell, URL acquisition or dynamic loader
is used. Errors do not echo payloads or private paths.

| Limit | Admission boundary |
| --- | --- |
| Encoded bytes per imported or stored dataset | 16 MiB, checked before parsing and during file reads |
| JSON container nesting | 12, scanned before the recursive JSON parser |
| Parsed tree nodes, including object keys | 1,000,000 |
| Decoded characters per key/string | 4,096; original identifier and decimal limits still apply |
| JSON integer magnitude | At most `2**63 - 1` |
| Accepted observations | 2–5,000 |
| Gap declarations | At most 1,024 |
| L2 levels | 1–20 on each side; truncation remains explicit |
| Datasets per storage root | 256; at most 272 enumerated entries including abandoned stages |

Bounds are fixed code constants, not document-supplied overrides. Byte bounds limit
allocation before tree-node validation; the parser is not a streaming constant-
memory parser. Storage scans validate one dataset at a time rather than retaining
all dataset bodies. Capacity is per explicitly provisioned root, not a global disk
quota; operators must provision disk and access appropriately.

## Chronology, completeness and provenance

The original frozen models validate nested L2 prices/sizes/counts, strict side
ordering, uncrossed top of book, component identity, market/source/simulation
consistency, increasing observation sequences, nondecreasing receipt times,
nonregressing observer generations, increasing present L2 source timestamps within
each observer generation, bounded/nonoverlapping ordered gaps, coverage endpoints
and the supplied dataset hash. Imports never sort, deduplicate, interpolate, trim
or repair invalid evidence.

The admission boundary adds:

- Explicit RFC3339 offset-aware timestamps with at most microsecond precision;
  numeric epoch coercion and naive times are rejected. No processing clock enters
  validation or economic identity. Source and receipt clocks remain independently
  attributed; no universal source-versus-receipt clock-skew bound is invented.
- Unique `(observer, generation, component kind, receipt instant)` identities.
  Source sequences, when supplied, must increase within that component generation.
  Missing source sequences stay absent. Gaps in provider source sequence numbers
  alone do not prove missing receipt events.
- Visible dataset-sequence skips require a declared positive gap between adjacent
  receipts. An observer/generation change requires DISCONNECT or OBSERVER_RESTART
  in that interval. A named gap must reference an observed instance. Equal receipt
  times remain legal for different components; zero-duration missing intervals
  cannot be used to justify a discontinuity. Interleaved concurrent observers are
  conservatively rejected unless these transition requirements can be met.

No sampling cadence is asserted, so ordinary time spacing alone cannot reveal
every missing event. Coverage stays PARTIAL or UNKNOWN, never continuous or
complete. Gaps remain supplied evidence, not proof that every loss was declared.
Context-only and book-only datasets remain legal incomplete evidence under 16.1A;
neither is promoted into a complete economic history. In the existing provenance
helper a context-only dataset can carry the verified-L2 *policy* label with zero
L2 observations; consumers must use its explicit L2/verified counts, not infer
the existence of L2 data from that category. That helper/contract is unchanged.

Funding, oracle, OI and source event timestamps that are missing remain null.
Perpetual context retains receipt time only. A book snapshot never establishes
intermediate trades, passive fills or queue position. No external provider/native
history, midprice, funding accrual, returns or performance is fabricated.

`canonical_bytes()` reserializes and reparses nested evidence, including forged or
mutated frozen instances. It stores sorted keys, UTC timestamps and existing
decimal strings. Equivalent key order/whitespace/timezone representations produce
the same canonical storage bytes and original content fingerprints. Existing
`describe_provenance()` supplies deterministic source/observation/gap hashes and
counts from read-back evidence. Import path, wall clock and random staging name
never enter economic identity. Decimal scale follows the original hash rules;
this phase does not redefine numeric identity or migrate fingerprints.

## Local filesystem security and transactions

Imports take a separate root and **one filename**: absolute filenames, separators,
parent traversal, NULs and dot entries are rejected. The root is walked from `/`
with directory descriptors and `O_NOFOLLOW`; symlinks in ancestors or the final
filename cannot escape the root. Files are opened nonblocking, checked with fstat
and bounded reads, and rejected if nonregular, multiply hardlinked, oversized or
changed in size/mtime/ctime while read. FIFOs/devices/directories are not parsed.
Concurrent pathname replacement cannot redirect an already pinned descriptor.
The input is a validated in-memory snapshot; this is not authentication of its
producer or a guarantee that a hostile file owner cannot race its own contents.

Storage requires an existing directory owned by the effective UID with **no group
or other permission bits**. Ancestors must also be controlled by the caller.
Dataset identifiers are hashed into fixed filenames, never interpolated into
paths; the original ID is checked on reads to detect collisions. IDs valid in
16.1A may contain slashes without becoming paths.

All cooperating operations take a shared/exclusive `flock` on the pinned root
inode. Every save revalidates evidence and existing committed entries; reused
dataset IDs or `(market, source kind, source ID)` identities are rejected, including
identical resubmissions. Use distinct source IDs for distinct chunks of a recording.
Lists detect duplicate stored source identities. A targeted read validates its own
entry; it does not audit unrelated files. Corruption is never silently overwritten.

Writes use unpredictable, exclusive 0600 staging files in the same directory,
full writes/flush/file-fsync, staged byte comparison, no-clobber hardlink publication,
stage removal, deterministic contract/hash/canonical-byte/filename read-back and
directory-fsync before success. Exceptions remove only the new transaction's inode
and staging file under the exclusive lock, including an interruption immediately
after successful publication. Readers cannot observe the transient hardlink state
or failed publication. Old committed datasets remain unchanged. Unexpected entries,
corrupted hashes, missing hashes, noncanonical bytes, substituted links, truncated
data or filename collisions fail closed. Abandoned hidden stages are not listed as
datasets; enumeration remains bounded.

This implementation requires local POSIX directory descriptors, `O_NOFOLLOW`,
`flock`, hardlinks and fsync; it does not claim Windows/NFS/object-store semantics.
No database, delete, overwrite, automatic recovery or multi-dataset transaction is
provided. Power loss/SIGKILL/filesystem failure may leave an abandoned stage or an
indeterminate **complete** commit; a crash between link and unlink yields an unsafe
link count and is rejected until an operator inspects it offline. Exception
rollback is tested on a functioning filesystem; persistent failure of cleanup or
fsync cannot be made durably recoverable by this API. Hashes/canonical checks are
not signatures and cannot detect an owner who rewrites both data and hashes.

## Executed acceptance and remaining gaps

Execution uses the repository's real dependencies and helpers, not stand-ins.
Python 3.12.14; pytest 8.4.2; Pydantic 2.14.3; official SDK 0.24.0. Dependency
installation used a workspace virtualenv and the existing backend test/redis extras:

```sh
python -m venv work/venv
work/venv/bin/python -m pip install -e './backend[test,redis]'
cd backend
../work/venv/bin/python -m pytest tests/test_phase161a_contracts.py -q
../work/venv/bin/python -m pytest tests/test_phase161a_contracts.py tests/test_phase161b_importers.py -q
timeout 300 ../work/venv/bin/python -m pytest tests -q -rs -o faulthandler_timeout=45
```

Final results (all 2,062 collected backend tests were executed or explicitly skipped):

| Run | Actual result |
| --- | --- |
| Native 16.1A contracts | 12 passed in 0.26s |
| Final 16.1A + 16.1B acceptance | 146 passed, 1 dependency deprecation warning in 3.20s |
| Final complete backend suite | 2,058 passed, 3 failed, 1 skipped, 1 dependency deprecation warning in 82.38s |
| Three failing checks on untouched base archive | Same 3 failed in 0.22s |
| Staged whitespace validation | `git diff --cached --check` passed |

An earlier broad run completed with 2,052 passed, 3 failed, 1 skipped in 85.87s,
before the last six adversarial cases were added. The three static failures all
identify existing text in `docs/PHASE155B_ACCEPTANCE.md`, not an operational
dependency or this change:

- `test_phase8_static.py::test_repository_contains_no_forbidden_oracle_provider_token`
- `test_phase9_static.py::test_phase9_does_not_create_github_actions_or_forbidden_oracle`
- `test_phase10_static.py::test_no_github_actions_or_forbidden_oracle_added`

Those exact checks also fail against a clean `git archive` of the base commit:

```sh
mkdir -p work/baseline
git archive 7001e070b7094c5fdcde055e3240cfb73c089a6b | tar -x -C work/baseline
cd work/baseline
../venv/bin/python -m pytest \
  backend/tests/test_phase8_static.py::test_repository_contains_no_forbidden_oracle_provider_token \
  backend/tests/test_phase9_static.py::test_phase9_does_not_create_github_actions_or_forbidden_oracle \
  backend/tests/test_phase10_static.py::test_no_github_actions_or_forbidden_oracle_added -q
```

They are documented, not suppressed or fixed by changing unrelated Phase 1–15.5
files. The one skip is
`test_agent_expansion.py::test_offline_training_optional_import_and_real_coefficient_export`:
scikit-learn is absent. A dependency deprecation warning concerns
Starlette's httpx TestClient support. An initial broad run in a network-restricted
sandbox stalled in TestClient; it was stopped and rerun with networking enabled
for the test runtime. No live venue or signing credential was configured or used.

Adversarial tests cover exact byte/nesting/node/string/integer/count limits, all
three markets and source kinds, false/forged assertions, malformed identity and
time fields, economic mutation, immutable nested evidence, duplicate receipts and
source sequences, generation rollback/reset, gaps, L2 ordering and truncation,
path/symlink/hardlink/FIFO/oversize/mutation attacks, compression bombs/archive
traversal without extraction, canonical read-back, storage corruption/collision,
duplicate admission races, capacity, interrupted/partial writes, rollback at
file-fsync/publication/read-back/directory-fsync, blocked readers during rollback,
independent roots and seeded actual PAPER authority with kill switch both off/on.

Security/acceptance limits: tests use declared fixture recordings, not acquired
licensed history. No independent data authenticity, completeness, licensing audit,
hostile-owner resistance, hardware power-loss recovery, multiprocess crash soak,
live-provider acceptance, benchmark, replay results or frontend validation is
claimed. Standalone live/long-duration acceptance scripts outside pytest collection
were not run. Replay compatibility means validated `phase16-replay-v1` read-back
only; replay execution belongs to a later phase. The PR remains DRAFT and must not
be merged automatically.
