"""Native import/storage acceptance, including malicious files and rollback."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import threading
from types import SimpleNamespace
import zipfile

from pydantic import ValidationError
import pytest

from app.research_replay import importers, storage, validation
from app.research_replay.importers import ImportAssertions, import_file
from app.research_replay.models import HistoricalDataset
from app.research_replay.provenance import describe_provenance
from app.research_replay.storage import (
    DuplicateIdentityError, HistoricalStorage, StorageCorruptionError, StorageError,
)
from app.research_replay.validation import (
    ImportValidationError, canonical_bytes, decode_payload, validate_bytes,
)
from test_phase161a_contracts import sample


@pytest.fixture
def payload():
    value = sample().model_dump(mode="json")
    value["dataset_fingerprint"] = None
    return value


def wire(value):
    return json.dumps(value, separators=(",", ":")).encode()


def assertion(value, **overrides):
    return ImportAssertions(market=overrides.get("market", f'{value["market"]}-PERP'),
        source_id=overrides.get("source_id", value["source"]["source_id"]),
        source_kind=overrides.get("source_kind", value["source"]["source_kind"]),
        permitted_use=overrides.get("permitted_use", True))


def admit(tmp_path, value, **overrides):
    (tmp_path / "capture.json").write_bytes(wire(value))
    return import_file(tmp_path, "capture.json", assertions=assertion(value, **overrides))


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "vault"
    root.mkdir(mode=0o700)
    return HistoricalStorage(root)


def entry(vault, dataset_id):
    return Path(vault.root) / (hashlib.sha256(dataset_id.encode()).hexdigest() + ".json")


@pytest.mark.parametrize("market", ["BTC", "ETH", "SOL"])
@pytest.mark.parametrize("native", [True, False])
def test_all_markets_and_source_kinds(tmp_path, market, native):
    value = sample(native=native).model_dump(mode="json")
    value["dataset_fingerprint"] = None
    value["market"] = value["source"]["market"] = market
    for point in value["observations"]:
        point["market"] = market
    result = admit(tmp_path, value)
    assert result.market == market and result.simulated is not native
    assert result.authority == "NONE" and result.read_only is True
    assert result.source.source_authenticated is False
    assert result.source.licensing_independently_verified is False


@pytest.mark.parametrize("change", [
    {"market": "SOL-PERP"}, {"market": "BTC"}, {"market": "DOGE-PERP"},
    {"source_id": "other"}, {"source_kind": "SYNTHETIC_FIXTURE"}, {"permitted_use": False},
])
def test_separate_caller_assertions_required(tmp_path, payload, change):
    with pytest.raises(ImportValidationError):
        admit(tmp_path, payload, **change)


@pytest.mark.parametrize("value", [True, False, 0, 1, "true"])
def test_permission_assertion_is_strict(payload, value):
    if type(value) is bool:
        assert assertion(payload, permitted_use=value).permitted_use is value
    else:
        with pytest.raises(ValidationError):
            assertion(payload, permitted_use=value)


def test_forged_assertion_revalidated(tmp_path, payload):
    (tmp_path / "capture.json").write_bytes(wire(payload))
    forged = assertion(payload).model_copy(update={"permitted_use": 1})
    with pytest.warns(UserWarning, match="serializer"), pytest.raises(ImportValidationError):
        import_file(tmp_path, "capture.json", assertions=forged)


@pytest.mark.parametrize("path,value", [
    (("contract_version",), "phase16-replay-v2"),
    (("source", "provider"), "KRAKEN"),
    (("source", "use_attestation"), "LICENSE_VERIFIED"),
    (("source", "source_id"), ""),
    (("source", "source_authenticated"), True),
    (("source", "source_authenticated"), 0),
    (("source", "licensing_independently_verified"), True),
    (("source", "market"), "ETH"),
    (("source", "collection_method"), "SYNTHETIC_GENERATOR"),
    (("simulated",), True), (("simulated",), 0),
    (("authority",), "TRADE"), (("read_only",), 1),
    (("coverage_status",), "COMPLETE"), (("continuous_history_verified",), True),
    (("coverage_end",), "2026-10-01T00:00:04Z"),
    (("observations", 0, "received_at"), "2026-10-01T00:00:00"),
    (("observations", 0, "received_at"), 1790812800),
    (("observations", 0, "received_at"), "2026-10-01T00:00:00.0000001Z"),
    (("observations", 1, "source_timestamp"), "2026-10-01T00:00:02Z"),
    (("observations", 0, "source_timestamp"), None),
    (("observations", 1, "sequence"), 1),
    (("observations", 1, "sequence"), True),
    (("observations", 1, "sequence"), "2"),
    (("observations", 1, "sequence"), 2**63),
    (("observations", 1, "connection_generation"), 0),
    (("observations", 1, "market"), "SOL"),
    (("observations", 0, "order_book", "bids", 0, "price"), "NaN"),
    (("observations", 0, "order_book", "bids", 0, "price"), "1e999999"),
    (("observations", 0, "order_book", "bids", 0, "price"), "9" * 81),
    (("observations", 0, "order_book", "bids", 0, "price"), 60001),
    (("observations", 0, "order_book", "bids", 0, "size"), "-1"),
    (("observations", 0, "order_book", "bids", 0, "order_count"), -1),
    (("observations", 1, "perp_context", "mark_price"), "0"),
    (("observations", 1, "perp_context", "open_interest_base"), "-1"),
    (("observations", 1, "perp_context", "passive_fills"), []),
    (("observations", 0, "queue_position"), 1),
])
def test_malformed_contracts_rejected(payload, path, value):
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ImportValidationError):
        validate_bytes(wire(payload))


def test_missing_version_and_unknown_fields(payload):
    del payload["contract_version"]
    with pytest.raises(ImportValidationError):
        validate_bytes(wire(payload))
    payload["contract_version"] = "phase16-replay-v1"
    payload["__reduce__"] = "execute"
    with pytest.raises(ImportValidationError):
        validate_bytes(wire(payload))


def test_no_invented_economics_and_immutable_nested_evidence(tmp_path, payload):
    payload["observations"][0].update(source_timestamp=None, source_event_time_verified=False)
    payload["observations"][1]["perp_context"] = {"mark_price": "60000"}
    result = admit(tmp_path, payload)
    context = result.observations[1].perp_context
    assert context.funding_rate is context.oracle_price is context.open_interest_base is None
    assert result.observations[0].source_timestamp is None
    assert describe_provenance(result).verified_l2_event_time_count == 0
    with pytest.raises(ValidationError):
        result.observations[0].sequence = 100
    with pytest.raises(ValidationError):
        result.observations[0].order_book.bids[0].size = "3"
    payload["observations"][0]["order_book"]["bids"][0]["size"] = "99"
    assert str(result.observations[0].order_book.bids[0].size) == "1"


def test_fingerprints_deterministic_and_mutations_detected(tmp_path, payload, vault):
    first = admit(tmp_path, payload)
    alternate = json.loads(canonical_bytes(first))
    for point in alternate["observations"]:
        for key in ("received_at", "source_timestamp"):
            if point[key] is not None:
                point[key] = datetime.fromisoformat(point[key]).astimezone(
                    timezone(timedelta(hours=2))).isoformat()
    for key in ("coverage_start", "coverage_end"):
        alternate[key] = datetime.fromisoformat(alternate[key]).astimezone(
            timezone(timedelta(hours=2))).isoformat()
    second = validate_bytes(json.dumps(alternate, indent=4).encode())
    assert canonical_bytes(first) == canonical_bytes(second)
    assert describe_provenance(first) == describe_provenance(second)
    stored = vault.save(first)
    assert stored == first == vault.read(first.dataset_id)
    assert canonical_bytes(stored) == entry(vault, first.dataset_id).read_bytes()
    assert stat.S_IMODE(entry(vault, first.dataset_id).stat().st_mode) == 0o600
    forged = first.model_copy(update={"simulated": True})
    with pytest.raises(ImportValidationError):
        vault.save(forged)
    changed = first.model_dump(mode="json")
    changed["observations"][0]["order_book"]["bids"][0]["size"] = "3"
    with pytest.raises(ImportValidationError):
        validate_bytes(wire(changed))
    changed["dataset_fingerprint"] = None
    assert validate_bytes(wire(changed)).dataset_fingerprint != first.dataset_fingerprint


def gap_for(payload, *, reason="DROPPED", observer=None):
    return {"start_at": payload["coverage_start"], "end_at": payload["coverage_end"],
            "reason": reason, "observer_instance_id": observer}


@pytest.mark.parametrize("field,value,reason", [
    ("sequence", 4, "DROPPED"), ("connection_generation", 2, "DISCONNECT"),
    ("observer_instance_id", "session-2", "OBSERVER_RESTART"),
])
def test_discontinuity_requires_declared_gap(payload, field, value, reason):
    payload["observations"][1][field] = value
    with pytest.raises(ImportValidationError, match="gap"):
        validate_bytes(wire(payload))
    payload["gaps"] = [gap_for(payload, reason=reason)]
    assert len(validate_bytes(wire(payload)).gaps) == 1


@pytest.mark.parametrize("change", [
    {"reason": "INFERRED"}, {"observer_instance_id": "missing"},
    {"start_at": "2026-09-30T00:00:00Z"},
    {"end_at": "2026-10-02T00:00:00Z"},
    {"end_at": "2026-10-01T00:00:00Z"},
])
def test_gap_declaration_integrity(payload, change):
    declaration = gap_for(payload)
    declaration.update(change)
    payload["gaps"] = [declaration]
    with pytest.raises(ImportValidationError):
        validate_bytes(wire(payload))


def test_overlapping_unordered_and_observation_containing_gaps(payload):
    payload["gaps"] = [gap_for(payload), gap_for(payload)]
    with pytest.raises(ImportValidationError):
        validate_bytes(wire(payload))
    original = deepcopy(payload["observations"][1])
    middle = deepcopy(original)
    middle.update(sequence=2, received_at="2026-10-01T00:00:01Z")
    original["sequence"] = 3
    payload["observations"] = [payload["observations"][0], middle, original]
    payload["gaps"] = [gap_for(payload)]
    with pytest.raises(ImportValidationError):
        validate_bytes(wire(payload))
    payload["gaps"] = []
    assert validate_bytes(wire(payload))
    payload["observations"].reverse()
    with pytest.raises(ImportValidationError):
        validate_bytes(wire(payload))


def test_duplicate_receipts_and_source_sequences(payload):
    first = payload["observations"][0]
    clone = deepcopy(first)
    clone.update(sequence=2, source_timestamp="2026-10-01T00:00:00Z")
    payload["observations"][1]["sequence"] = 3
    payload["observations"].insert(1, clone)
    with pytest.raises(ImportValidationError, match="duplicate"):
        validate_bytes(wire(payload))
    clone["received_at"] = "2026-10-01T00:00:01Z"
    first["source_sequence"] = clone["source_sequence"] = 5
    with pytest.raises(ImportValidationError, match="source sequence"):
        validate_bytes(wire(payload))
    clone["source_sequence"] = 4
    with pytest.raises(ImportValidationError):
        validate_bytes(wire(payload))
    clone["source_sequence"] = 6
    assert validate_bytes(wire(payload))
    clone["source_timestamp"] = first["source_timestamp"]
    with pytest.raises(ImportValidationError):
        validate_bytes(wire(payload))


def test_generation_reset_and_regression(payload):
    second = deepcopy(payload["observations"][0])
    second.update(sequence=2, received_at="2026-10-01T00:00:03Z",
                  source_sequence=1, connection_generation=2)
    payload["observations"][0]["source_sequence"] = 10
    payload["observations"][1] = second
    payload["gaps"] = [gap_for(payload, reason="DISCONNECT")]
    assert validate_bytes(wire(payload))
    second["connection_generation"] = 0
    with pytest.raises(ImportValidationError):
        validate_bytes(wire(payload))


@pytest.mark.parametrize("raw", [b"", b"[]", b"null", b"{}{}", b"{", b"\xff",
    b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1.0}', b'{"x":1e9999}',
    b'{"x":1,"x":2}', b'{"x":{"a":1,"a":2}}', b'{"x":"\\ud800"}',
    b'{"x":999999999999999999999999999999999999}',
    b'\xef\xbb\xbf{}', b'!!python/object/apply:os.system ["touch bad"]',
    b'cos\nsystem\n(S"touch bad"\ntR.', b'<html><script>alert(1)</script></html>',
])
def test_malicious_parser_inputs(raw):
    with pytest.raises(ImportValidationError):
        decode_payload(raw)


def test_parser_budget_boundaries():
    assert decode_payload(b"{}" + b" " * (validation.MAX_BYTES - 2)) == {}
    with pytest.raises(ImportValidationError):
        decode_payload(b"{}" + b" " * (validation.MAX_BYTES - 1))
    assert decode_payload(b'{"x":' + b"[" * 11 + b"0" + b"]" * 11 + b"}")
    with pytest.raises(ImportValidationError, match="nesting"):
        decode_payload(b'{"x":' + b"[" * 12 + b"0" + b"]" * 12 + b"}")
    assert decode_payload(wire({"x": "[\\\"" * 100}))
    assert decode_payload(wire({"x": "a" * validation.MAX_STRING}))
    with pytest.raises(ImportValidationError):
        decode_payload(wire({"x": "a" * (validation.MAX_STRING + 1)}))
    assert decode_payload(wire({"x": validation.MAX_INTEGER}))
    with pytest.raises(ImportValidationError):
        decode_payload(wire({"x": validation.MAX_INTEGER + 1}))


def test_node_budget_exact_boundary():
    raw = b'{"x":[' + b"0," * (validation.MAX_NODES - 4) + b"0]}"
    assert decode_payload(raw)
    with pytest.raises(ImportValidationError, match="node"):
        decode_payload(raw[:-2] + b",0]}")


@pytest.mark.parametrize("count,accepted", [(1, False), (2, True), (5000, True), (5001, False)])
def test_observation_count_bounds(payload, count, accepted):
    base = datetime(2026, 10, 1, tzinfo=timezone.utc)
    template = payload["observations"][1]
    points = []
    for i in range(count):
        point = deepcopy(template)
        point.update(sequence=i, received_at=(base + timedelta(seconds=i)).isoformat())
        points.append(point)
    payload.update(observations=points, coverage_start=points[0]["received_at"],
                   coverage_end=points[-1]["received_at"])
    if accepted:
        assert len(validate_bytes(wire(payload)).observations) == count
    else:
        with pytest.raises(ImportValidationError):
            validate_bytes(wire(payload))


@pytest.mark.parametrize("count,accepted", [(20, True), (21, False)])
def test_l2_depth_bounds(payload, count, accepted):
    book = payload["observations"][0]["order_book"]
    book["bids"] = [{"price": str(60000-i), "size": "1"} for i in range(count)]
    book["asks"] = [{"price": str(60001+i), "size": "1"} for i in range(count)]
    book["truncated"] = True
    if accepted:
        assert validate_bytes(wire(payload)).observations[0].order_book.truncated
    else:
        with pytest.raises(ImportValidationError):
            validate_bytes(wire(payload))


@pytest.mark.parametrize("side", ["bids", "asks"])
def test_duplicate_and_unordered_book_levels(payload, side):
    levels = payload["observations"][0]["order_book"][side]
    levels.append(deepcopy(levels[0]))
    with pytest.raises(ImportValidationError):
        validate_bytes(wire(payload))
    levels[1]["price"] = "60002" if side == "bids" else "59999"
    with pytest.raises(ImportValidationError):
        validate_bytes(wire(payload))


@pytest.mark.parametrize("count,accepted", [(1024, True), (1025, False)])
def test_gap_count_bounds(payload, count, accepted):
    base = datetime(2026, 10, 1, tzinfo=timezone.utc)
    payload["gaps"] = [{"start_at": (base+timedelta(milliseconds=i)).isoformat(),
                        "end_at": (base+timedelta(milliseconds=i+1)).isoformat(),
                        "reason": "UNKNOWN_COVERAGE"} for i in range(count)]
    if accepted:
        assert len(validate_bytes(wire(payload)).gaps) == count
    else:
        with pytest.raises(ImportValidationError):
            validate_bytes(wire(payload))


@pytest.mark.parametrize("name", ["../capture.json", "/tmp/capture.json", "a/b", "a\\b", ".", "..", "", "a\x00b"])
def test_path_traversal_rejected(tmp_path, payload, name):
    with pytest.raises(ImportValidationError):
        import_file(tmp_path, name, assertions=assertion(payload))


def test_symlinks_hardlinks_special_files_and_root_escape(tmp_path, payload):
    actual = tmp_path / "actual"
    actual.mkdir()
    (actual / "capture.json").write_bytes(wire(payload))
    (tmp_path / "alias").symlink_to(actual, target_is_directory=True)
    with pytest.raises(ImportValidationError):
        import_file(tmp_path / "alias", "capture.json", assertions=assertion(payload))
    with pytest.raises(ImportValidationError):
        import_file(tmp_path / "alias" / ".." / "actual", "capture.json", assertions=assertion(payload))
    (tmp_path / "linked.json").symlink_to(actual / "capture.json")
    os.link(actual / "capture.json", tmp_path / "hard.json")
    os.mkfifo(tmp_path / "pipe.json")
    for filename in ("linked.json", "hard.json", "pipe.json", "actual", "missing"):
        with pytest.raises(ImportValidationError):
            import_file(tmp_path, filename, assertions=assertion(payload))


def test_compressed_and_executable_files_never_expanded(tmp_path, payload):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("../escaped", b"x" * 1_000_000)
    for raw in (gzip.compress(b"x" * (validation.MAX_BYTES + 1)), out.getvalue(),
                b'#!/bin/sh\ntouch escaped\n'):
        (tmp_path / "capture.json").write_bytes(raw)
        with pytest.raises(ImportValidationError):
            import_file(tmp_path, "capture.json", assertions=assertion(payload))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["capture.json"]


def test_oversized_file_and_mutation_during_read(tmp_path, payload, monkeypatch):
    path = tmp_path / "capture.json"
    with path.open("wb") as stream:
        stream.truncate(validation.MAX_BYTES + 1)
    with pytest.raises(ImportValidationError):
        import_file(tmp_path, path.name, assertions=assertion(payload))
    path.write_bytes(wire(payload))
    original = os.fstat
    calls = 0
    def changing(fd):
        nonlocal calls
        calls += 1
        result = original(fd)
        if calls == 2:
            return SimpleNamespace(st_size=result.st_size, st_mtime_ns=result.st_mtime_ns + 1,
                                   st_ctime_ns=result.st_ctime_ns)
        return result
    monkeypatch.setattr(importers.os, "fstat", changing)
    with pytest.raises(ImportValidationError, match="changed"):
        import_file(tmp_path, path.name, assertions=assertion(payload))


def test_duplicate_ids_sources_and_independent_vaults(vault, tmp_path, payload):
    dataset = validate_bytes(wire(payload))
    vault.save(dataset)
    with pytest.raises(DuplicateIdentityError):
        vault.save(dataset)
    payload["dataset_id"] = "alias-dataset"
    with pytest.raises(DuplicateIdentityError, match="source identity"):
        vault.save(validate_bytes(wire(payload)))
    payload["dataset_id"] = dataset.dataset_id
    payload["source"]["source_id"] = "different-source"
    with pytest.raises(DuplicateIdentityError, match="dataset identity"):
        vault.save(validate_bytes(wire(payload)))
    other_root = tmp_path / "other"
    other_root.mkdir(mode=0o700)
    other = HistoricalStorage(other_root)
    assert other.list_ids() == ()
    assert other.save(dataset) == dataset
    assert vault.list_ids() == (dataset.dataset_id,)


def test_preexisting_duplicate_source_identity_is_corruption(vault, payload):
    vault.save(validate_bytes(wire(payload)))
    payload["dataset_id"] = "copied-identity"
    clone = validate_bytes(wire(payload))
    entry(vault, clone.dataset_id).write_bytes(canonical_bytes(clone))
    with pytest.raises(StorageCorruptionError, match="duplicate"):
        vault.list_ids()
    payload["dataset_id"] = payload["source"]["source_id"] = "new"
    with pytest.raises(StorageCorruptionError, match="duplicate"):
        vault.save(validate_bytes(wire(payload)))


def test_concurrent_duplicate_admission(vault, payload):
    dataset = validate_bytes(wire(payload))
    def save():
        try:
            vault.save(dataset)
            return "saved"
        except DuplicateIdentityError:
            return "duplicate"
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: save(), range(2)))
    assert sorted(results) == ["duplicate", "saved"]
    assert vault.read(dataset.dataset_id) == dataset


def test_readers_cannot_observe_publication_before_rollback(vault, payload, monkeypatch):
    old = vault.save(validate_bytes(wire(payload)))
    payload["dataset_id"] = payload["source"]["source_id"] = "failed"
    incoming = validate_bytes(wire(payload))
    published, release, reader_started = threading.Event(), threading.Event(), threading.Event()
    real_fsync = os.fsync
    fired = False
    def fail_after_publication(fd):
        nonlocal fired
        if not fired and stat.S_ISDIR(os.fstat(fd).st_mode):
            fired = True
            published.set()
            assert release.wait(5)
            raise OSError("injected commit durability failure")
        return real_fsync(fd)
    def reader():
        reader_started.set()
        return vault.list_ids()
    monkeypatch.setattr(storage.os, "fsync", fail_after_publication)
    with ThreadPoolExecutor(max_workers=2) as executor:
        writer = executor.submit(vault.save, incoming)
        try:
            assert published.wait(5)
            reading = executor.submit(reader)
            assert reader_started.wait(5)
            assert not reading.done()
        finally:
            release.set()
        with pytest.raises(StorageError):
            writer.result(timeout=5)
        assert reading.result(timeout=5) == (old.dataset_id,)


def test_partial_write_failure_cleans_stage(vault, payload, monkeypatch):
    real_fdopen = os.fdopen
    class BrokenWriter:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.stream.close()
        def fileno(self):
            return self.stream.fileno()
        def write(self, raw):
            self.stream.write(raw[:20])
            self.stream.flush()
            raise OSError("injected partial write")
    def fdopen(fd, mode, **kwargs):
        stream = real_fdopen(fd, mode, **kwargs)
        return BrokenWriter(stream) if mode == "wb" else stream
    monkeypatch.setattr(storage.os, "fdopen", fdopen)
    with pytest.raises(StorageError):
        vault.save(validate_bytes(wire(payload)))
    assert vault.list_ids() == () and not list(Path(vault.root).iterdir())


def test_interruption_immediately_after_link_rolls_back(vault, payload, monkeypatch):
    real_link = os.link
    def interrupted(*args, **kwargs):
        real_link(*args, **kwargs)
        raise KeyboardInterrupt("after successful link before return")
    monkeypatch.setattr(storage.os, "link", interrupted)
    with pytest.raises(KeyboardInterrupt):
        vault.save(validate_bytes(wire(payload)))
    assert vault.list_ids() == () and not list(Path(vault.root).iterdir())


@pytest.mark.parametrize("kind", ["truncate", "economic", "fingerprint", "missing_hash", "whitespace", "symlink", "hardlink"])
def test_storage_corruption_fails_closed(vault, tmp_path, payload, kind):
    dataset = vault.save(validate_bytes(wire(payload)))
    path = entry(vault, dataset.dataset_id)
    original = path.read_bytes()
    if kind == "truncate":
        path.write_bytes(original[:30])
    elif kind == "economic":
        path.write_bytes(original.replace(b'"size":"1"', b'"size":"9"'))
    elif kind == "fingerprint":
        path.write_bytes(original.replace(dataset.dataset_fingerprint.encode(), b"0" * 64))
    elif kind == "missing_hash":
        value = json.loads(original)
        del value["dataset_fingerprint"]
        path.write_bytes(wire(value))
    elif kind == "whitespace":
        path.write_bytes(original + b" ")
    else:
        external = tmp_path / "external.json"
        external.write_bytes(original)
        path.unlink()
        if kind == "symlink":
            path.symlink_to(external)
        else:
            os.link(external, path)
    with pytest.raises(StorageCorruptionError):
        vault.read(dataset.dataset_id)
    with pytest.raises(StorageCorruptionError):
        vault.list_ids()
    payload["dataset_id"] = "new"
    payload["source"]["source_id"] = "new"
    with pytest.raises(StorageCorruptionError):
        vault.save(validate_bytes(wire(payload)))


def test_storage_collision_and_unexpected_entries(vault, payload, monkeypatch):
    dataset = vault.save(validate_bytes(wire(payload)))
    filename = entry(vault, dataset.dataset_id).name
    monkeypatch.setattr(storage, "_filename", lambda _: filename)
    payload["dataset_id"] = "collision"
    payload["source"]["source_id"] = "collision"
    with pytest.raises(StorageCorruptionError, match="collision"):
        vault.save(validate_bytes(wire(payload)))
    with pytest.raises(StorageCorruptionError, match="collision"):
        vault.read("collision")
    (Path(vault.root) / "unexpected").write_text("x")
    with pytest.raises(StorageCorruptionError):
        vault.list_ids()


@pytest.mark.parametrize("failure", ["file_fsync", "link", "readback", "directory_fsync"])
def test_rollback_preserves_old_data_and_hides_failed_import(vault, payload, monkeypatch, failure):
    old = vault.save(validate_bytes(wire(payload)))
    payload["dataset_id"] = payload["source"]["source_id"] = "second"
    new = validate_bytes(wire(payload))
    real_fsync, real_link, real_read = os.fsync, os.link, storage.read_local_file
    fired = False
    def sync(fd):
        nonlocal fired
        is_directory = stat.S_ISDIR(os.fstat(fd).st_mode)
        if not fired and ((failure == "file_fsync" and not is_directory) or
                          (failure == "directory_fsync" and is_directory)):
            fired = True
            raise OSError("injected fsync failure")
        return real_fsync(fd)
    def link(*args, **kwargs):
        if failure == "link":
            raise OSError("injected publication failure")
        return real_link(*args, **kwargs)
    def read(fd, name):
        if failure == "readback" and name == entry(vault, new.dataset_id).name:
            raise OSError("injected read-back failure")
        return real_read(fd, name)
    monkeypatch.setattr(storage.os, "fsync", sync)
    monkeypatch.setattr(storage.os, "link", link)
    monkeypatch.setattr(storage, "read_local_file", read)
    with pytest.raises(StorageError):
        vault.save(new)
    assert vault.list_ids() == (old.dataset_id,)
    assert vault.read(old.dataset_id) == old
    assert sorted(p.name for p in Path(vault.root).iterdir()) == [entry(vault, old.dataset_id).name]


def test_capacity_and_abandoned_stage_are_bounded(vault, payload, monkeypatch):
    monkeypatch.setattr(storage, "MAX_DATASETS", 1)
    dataset = vault.save(validate_bytes(wire(payload)))
    (Path(vault.root) / ".stage-abandoned").write_text("incomplete")
    assert vault.list_ids() == (dataset.dataset_id,)
    payload["dataset_id"] = payload["source"]["source_id"] = "second"
    with pytest.raises(StorageError, match="capacity"):
        vault.save(validate_bytes(wire(payload)))
    for i in range(17):
        (Path(vault.root) / f".stage-{i}").write_text("x")
    with pytest.raises(StorageCorruptionError, match="too many"):
        vault.list_ids()


def test_storage_root_permissions_and_symlinks(tmp_path, payload):
    root = tmp_path / "root"
    root.mkdir(mode=0o755)
    root.chmod(0o755)  # Test the actual permission bits, independently of umask.
    with pytest.raises(StorageError, match="owner-only"):
        HistoricalStorage(root).save(validate_bytes(wire(payload)))
    root.chmod(0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(StorageError):
        HistoricalStorage(alias).list_ids()


def test_identifiers_are_data_never_storage_paths(vault, payload):
    payload["dataset_id"] = "capture/../../outside"
    dataset = vault.save(validate_bytes(wire(payload)))
    assert vault.read(dataset.dataset_id) == dataset
    assert all(len(p.name) == 69 for p in Path(vault.root).iterdir())


def test_no_runtime_modules_import_the_new_boundary():
    app = Path(__file__).parents[1] / "app"
    forbidden = ("research_replay.importers", "research_replay.storage", "research_replay.validation")
    for path in app.rglob("*.py"):
        if "research_replay" not in path.parts:
            assert not any(name in path.read_text() for name in forbidden), str(path)


@pytest.mark.parametrize("kill", [False, True])
async def test_import_storage_leave_seeded_paper_authority_unchanged(tmp_path, vault, payload, kill):
    from decimal import Decimal
    from app.config import Settings
    from app.runtime import HyperAmmRuntime
    from app.execution.models import OrderRequest
    from app.market_data.mock import MockMarketDataAdapter
    from test_phase14_research_vault import authority

    rt = HyperAmmRuntime(Settings(_env_file=None))
    frame = MockMarketDataAdapter().snapshot_for(4)
    await rt.market._accept(frame)
    await rt.refresh_once()
    await rt.paper.submit_orders([OrderRequest(client_order_id="161b-seed", market="ETH",
        side="BID", price=frame.best_ask, size=Decimal(".1"))])
    await rt.refresh_once()
    rt.strategy.running = True
    await rt._execution_authority()
    async with rt.execution_lock:
        await rt.orders.reconcile_locked(rt.config.market, rt.quotes,
            rt.config.replace_tolerance_bps, rt.config.size_tolerance)
    rt.accounting_service.reserve(rt.quotes, await rt.execution.get_open_orders())
    if kill:
        await rt.activate_kill()
        await rt.refresh_once()
    assert rt.paper.fills.all() and rt.accounting_service.ledger.version > 1
    before = authority(rt)
    services = tuple(id(x) for x in (rt.market, rt.perp_context_service, rt.reference_service))
    for market in ("BTC", "ETH", "SOL"):
        value = deepcopy(payload)
        value["dataset_id"] = market
        value["market"] = value["source"]["market"] = market
        for point in value["observations"]:
            point["market"] = market
        dataset = admit(tmp_path, value)
        assert vault.save(dataset) == vault.read(dataset.dataset_id)
        with pytest.raises(DuplicateIdentityError):
            vault.save(dataset)
        value["observations"][0]["sequence"] = 99
        with pytest.raises(ImportValidationError):
            admit(tmp_path, value)
    assert authority(rt) == before
    assert services == tuple(id(x) for x in (rt.market, rt.perp_context_service, rt.reference_service))
