"""Explicit local-file import. No acquisition, decompression or runtime wiring."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import PurePath
import stat

from pydantic import StrictBool

from app.market_data.live_models import Evidence
from .models import HistoricalDataset, Identifier, SourceKind
from .validation import ImportValidationError, MAX_BYTES, validate_bytes


class ImportAssertions(Evidence):
    """Separate caller assertions must match the file; no authenticated rights."""

    market: str
    source_id: Identifier
    source_kind: SourceKind
    permitted_use: StrictBool


@contextmanager
def open_directory(path):
    """Walk from / using pinned descriptors; reject symlinks in every component."""
    path = os.fspath(path)
    if not isinstance(path, str) or "\x00" in path or ".." in PurePath(path).parts:
        raise ImportValidationError("unsafe directory path")
    absolute = os.path.abspath(path)
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in PurePath(absolute).parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def read_local_file(directory_fd: int, filename: str) -> bytes:
    """Single regular, unlinked-to-others file; bounded read, no FIFO/device wait."""
    if (not isinstance(filename, str) or not filename or filename in (".", "..") or
            "/" in filename or "\\" in filename or "\x00" in filename):
        raise ImportValidationError("single local filename required")
    fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_BYTES:
            raise ImportValidationError("bounded regular file required")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(MAX_BYTES + 1)
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns) or len(raw) != before.st_size:
            raise ImportValidationError("file changed during read")
        if len(raw) > MAX_BYTES:
            raise ImportValidationError("payload byte limit exceeded")
        return raw
    finally:
        os.close(fd)


def import_file(root, filename: str, *, assertions: ImportAssertions) -> HistoricalDataset:
    """Read one JSON dataset under an explicit root, with no storage side effect.

    Wire markets remain BTC/ETH/SOL per 16.1A; caller uses display IDs BTC-PERP,
    ETH-PERP, SOL-PERP. Synthetic fixtures require the same explicit use assertion.
    """
    # Revalidate: frozen models can still be forged with model_construct/copy.
    try:
        assertions = ImportAssertions.model_validate(assertions.model_dump())
    except (ValueError, AttributeError):
        raise ImportValidationError("explicit import assertions required") from None
    if assertions.permitted_use is not True:
        raise ImportValidationError("caller must assert permitted use")
    if assertions.market not in ("BTC-PERP", "ETH-PERP", "SOL-PERP"):
        raise ImportValidationError("unsupported historical market")
    try:
        with open_directory(root) as directory_fd:
            dataset = validate_bytes(read_local_file(directory_fd, filename))
    except OSError:
        raise ImportValidationError("unsafe or unreadable local import") from None
    if (assertions.market != f"{dataset.market}-PERP" or
            assertions.source_id != dataset.source.source_id or
            assertions.source_kind != dataset.source.source_kind):
        raise ImportValidationError("caller and file source identity mismatch")
    return dataset
