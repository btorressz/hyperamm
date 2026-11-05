"""Bounded, fail-closed admission for Phase 16 evidence (no replay authority)."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re

from pydantic import ValidationError

from .models import CONTRACT_VERSION, HistoricalDataset

MAX_BYTES = 16 * 1024 * 1024
MAX_DEPTH = 12
MAX_NODES = 1_000_000
MAX_STRING = 4096
MAX_INTEGER = 2**63 - 1


class ImportValidationError(ValueError):
    """Untrusted evidence failed admission; messages never include wire data."""


def _reject(message="invalid historical input"):
    raise ImportValidationError(message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _reject("duplicate JSON key")
        result[key] = value
    return result


def _integer(value):
    if len(value.lstrip("-")) > 19:
        _reject("integer limit exceeded")
    result = int(value)
    if abs(result) > MAX_INTEGER:
        _reject("integer limit exceeded")
    return result


def decode_payload(raw: bytes) -> dict:
    """Only UTF-8 JSON, never archives, pickle, YAML, executable or remote input.

    Scan nesting *before* invoking the recursive JSON parser. All budgets are
    fixed rather than controlled by untrusted document fields.
    """
    if type(raw) is not bytes or not raw or len(raw) > MAX_BYTES:
        _reject("payload byte limit or type")
    try:
        wire = raw.decode("utf-8")
    except UnicodeError:
        _reject("UTF-8 JSON required")
    depth, quoted, escaped = 0, False, False
    for char in wire:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                _reject("payload nesting limit exceeded")
        elif char in "]}":
            depth -= 1
    try:
        value = json.loads(wire, object_pairs_hook=_pairs, parse_int=_integer,
                           parse_float=lambda _: _reject("JSON floats forbidden; use decimal strings"),
                           parse_constant=lambda _: _reject("nonfinite JSON forbidden"))
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, ImportValidationError):
            raise
        raise ImportValidationError("malformed JSON") from None
    if type(value) is not dict:
        _reject("dataset object required")
    pending, count = [value], 0
    while pending:
        item = pending.pop()
        count += 1
        if count > MAX_NODES:
            _reject("payload node limit exceeded")
        if isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, str):
            if len(item) > MAX_STRING or any(0xD800 <= ord(c) <= 0xDFFF for c in item):
                _reject("invalid or oversized string")
    return value


_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$")
_TIMES = {"received_at", "source_timestamp", "coverage_start", "coverage_end", "start_at", "end_at"}
_BOOLS = {"simulated", "read_only", "source_authenticated", "licensing_independently_verified",
          "continuous_history_verified", "source_event_time_verified", "truncated"}


def _validate_payload(value: dict) -> HistoricalDataset:
    """Revalidate from primitives, including caller-mutated/model_copy evidence.

    Existing 16.1A models remain unchanged. This boundary additionally requires
    explicit version, RFC3339 times and declarations for visible discontinuities.
    """
    if value.get("contract_version") != CONTRACT_VERSION:
        _reject("explicit phase16-replay-v1 contract required")
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            for key, entry in item.items():
                if key in _BOOLS and type(entry) is not bool:
                    _reject("boolean assertion required")
                if key in _TIMES and entry is not None:
                    if not isinstance(entry, str) or not _TIME.fullmatch(entry):
                        _reject("RFC3339 timestamp required")
                pending.append(entry)
        elif isinstance(item, list):
            pending.extend(item)
    try:
        dataset = HistoricalDataset.model_validate(value)
    except (ValidationError, ValueError, OverflowError):
        raise ImportValidationError("historical contract or fingerprint invalid") from None
    observers = {p.observer_instance_id for p in dataset.observations}
    for gap in dataset.gaps:
        if gap.observer_instance_id is not None and gap.observer_instance_id not in observers:
            _reject("gap references unknown observer")
    seen_receipts = set()
    source_sequences: dict[tuple, int] = {}
    previous = None
    for point in dataset.observations:
        identity = (point.observer_instance_id, point.connection_generation, point.kind, point.received_at)
        if identity in seen_receipts:
            _reject("duplicate component receipt identity")
        seen_receipts.add(identity)
        key = (point.observer_instance_id, point.connection_generation, point.kind)
        if point.source_sequence is not None:
            last = source_sequences.get(key)
            if last is not None and point.source_sequence <= last:
                _reject("duplicate or regressing source sequence")
            source_sequences[key] = point.source_sequence
        if previous is not None:
            restarted = (point.observer_instance_id != previous.observer_instance_id or
                         point.connection_generation != previous.connection_generation)
            skipped = point.sequence != previous.sequence + 1
            if restarted or skipped:
                reasons = {"OBSERVER_RESTART", "DISCONNECT"} if restarted else {
                    "DROPPED", "DISCONNECT", "MISSING_SOURCE", "UNKNOWN_COVERAGE", "OBSERVER_RESTART"}
                if not any(previous.received_at <= g.start_at < g.end_at <= point.received_at
                           and g.reason in reasons
                           and g.observer_instance_id in (None, point.observer_instance_id)
                           for g in dataset.gaps):
                    _reject("sequence or observer discontinuity requires explicit gap")
        previous = point
    return dataset


def validate_bytes(raw: bytes) -> HistoricalDataset:
    return _validate_payload(decode_payload(raw))


def canonical_bytes(dataset: HistoricalDataset) -> bytes:
    """Canonical storage form, preserving the established content fingerprint.

    UTC timestamps, sorted keys, decimal strings, no clock or filesystem paths.
    """
    try:
        value = dataset.model_dump(mode="json")
        pending = [value]
        while pending:
            item = pending.pop()
            if isinstance(item, dict):
                for key, entry in item.items():
                    if key in _TIMES and isinstance(entry, str) and _TIME.fullmatch(entry):
                        item[key] = datetime.fromisoformat(entry).astimezone(timezone.utc).isoformat()
                    else:
                        pending.append(entry)
            elif isinstance(item, list):
                pending.extend(item)
        raw = json.dumps(value, sort_keys=True,
                         separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise ImportValidationError("cannot serialize historical evidence") from None
    validate_bytes(raw)
    return raw
