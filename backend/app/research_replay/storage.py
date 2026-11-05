"""Private, bounded POSIX local evidence vault; deliberately no runtime hooks.

The caller provisions an owner-only directory. Cooperating readers/writers lock
its pinned inode. One fully validated file becomes visible per transaction.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import os
import re
import secrets

from .importers import open_directory, read_local_file
from .models import HistoricalDataset
from .validation import ImportValidationError, canonical_bytes, validate_bytes

MAX_DATASETS = 256
_ENTRY = re.compile(r"^[0-9a-f]{64}\.json$")


class StorageError(ValueError):
    pass


class DuplicateIdentityError(StorageError):
    pass


class StorageCorruptionError(StorageError):
    pass


def _filename(dataset_id: str) -> str:
    if not isinstance(dataset_id, str) or not 1 <= len(dataset_id) <= 120:
        raise StorageError("invalid dataset identity")
    # Identifiers are data, never paths (16.1A permits '/', ':' and '..').
    return hashlib.sha256(dataset_id.encode("utf-8")).hexdigest() + ".json"


def _source_identity(dataset):
    return dataset.market, dataset.source.source_kind, dataset.source.source_id


class HistoricalStorage:
    """Append-only admission, bounded to 256 datasets; no overwrite/delete API.

    Atomicity requires a local POSIX filesystem with flock, hard links and fsync.
    The root and its ancestors must be controlled by the caller. Content hashes
    detect corruption, not a malicious owner able to rewrite hashes and files.
    """

    def __init__(self, root):
        self.root = os.fspath(root)

    @contextmanager
    def _locked(self, *, exclusive):
        try:
            with open_directory(self.root) as fd:
                info = os.fstat(fd)
                if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                    raise StorageError("storage root must be owner-only")
                fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
                try:
                    yield fd
                finally:
                    fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            raise StorageError("local storage operation failed") from None

    @staticmethod
    def _entries(fd):
        entries = []
        scanned = 0
        # scandir bounds enumeration without allocating an unbounded listdir.
        with os.scandir(fd) as iterator:
            for entry in iterator:
                scanned += 1
                if scanned > MAX_DATASETS + 16:
                    raise StorageCorruptionError("too many storage entries, including abandoned stages")
                # Interrupted pre-publication staging files are never admitted.
                if entry.name.startswith(".stage-"):
                    continue
                if not _ENTRY.fullmatch(entry.name):
                    raise StorageCorruptionError("unexpected storage entry")
                entries.append(entry.name)
                if len(entries) > MAX_DATASETS:
                    raise StorageCorruptionError("storage capacity exceeded")
        return sorted(entries)

    @staticmethod
    def _read(fd, name):
        try:
            raw = read_local_file(fd, name)
            dataset = validate_bytes(raw)
            if (dataset.dataset_fingerprint is None or canonical_bytes(dataset) != raw or
                    _filename(dataset.dataset_id) != name):
                raise StorageCorruptionError("storage identity or canonical content mismatch")
            return dataset
        except (OSError, ImportValidationError):
            raise StorageCorruptionError("stored dataset corrupt or unsafe") from None

    def read(self, dataset_id: str) -> HistoricalDataset:
        name = _filename(dataset_id)
        with self._locked(exclusive=False) as fd:
            dataset = self._read(fd, name)
            if dataset.dataset_id != dataset_id:
                raise StorageCorruptionError("dataset identity hash collision")
            return dataset

    def list_ids(self) -> tuple[str, ...]:
        with self._locked(exclusive=False) as fd:
            ids, identities = [], set()
            for name in self._entries(fd):
                dataset = self._read(fd, name)
                identity = _source_identity(dataset)
                if identity in identities:
                    raise StorageCorruptionError("duplicate stored source identity")
                identities.add(identity)
                ids.append(dataset.dataset_id)
            return tuple(sorted(ids))

    def save(self, dataset: HistoricalDataset) -> HistoricalDataset:
        # Serialization + parse forces nested revalidation even for model_copy or
        # object.__setattr__ mutations. Never trust frozen-instance shortcuts.
        raw = canonical_bytes(dataset)
        admitted = validate_bytes(raw)
        name = _filename(admitted.dataset_id)
        with self._locked(exclusive=True) as fd:
            entries = self._entries(fd)
            identities = set()
            for existing_name in entries:
                existing = self._read(fd, existing_name)
                identity = _source_identity(existing)
                if identity in identities:
                    raise StorageCorruptionError("duplicate stored source identity")
                identities.add(identity)
                if existing_name == name:
                    if existing.dataset_id != admitted.dataset_id:
                        raise StorageCorruptionError("dataset identity hash collision")
                    raise DuplicateIdentityError("dataset identity already stored")
                if _source_identity(existing) == _source_identity(admitted):
                    raise DuplicateIdentityError("source identity already stored")
            if len(entries) >= MAX_DATASETS:
                raise StorageError("storage capacity reached")
            stage = ".stage-" + secrets.token_hex(16)
            created = False
            stage_info = None
            try:
                stage_fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                   0o600, dir_fd=fd)
                created = True
                with os.fdopen(stage_fd, "wb") as stream:
                    stage_info = os.fstat(stream.fileno())
                    if stream.write(raw) != len(raw):
                        raise StorageError("short staged write")
                    stream.flush()
                    os.fsync(stream.fileno())
                if read_local_file(fd, stage) != raw:
                    raise StorageCorruptionError("staged content mismatch")
                # No-clobber publication. The exclusive lock hides the transient
                # second hard link and all rollback work from API readers.
                os.link(stage, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
                os.unlink(stage, dir_fd=fd)
                created = False
                stored = self._read(fd, name)
                if stored != admitted:
                    raise StorageCorruptionError("read-back mismatch")
                os.fsync(fd)
                return stored
            except BaseException:
                # An interruption can arrive after link() succeeds but before
                # Python records success. Remove only our inode, never a
                # preexisting destination when no-clobber publication failed.
                if stage_info is not None:
                    try:
                        final_info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                        if (final_info.st_dev, final_info.st_ino) == (stage_info.st_dev, stage_info.st_ino):
                            os.unlink(name, dir_fd=fd)
                    except FileNotFoundError:
                        pass
                if created:
                    try:
                        os.unlink(stage, dir_fd=fd)
                    except FileNotFoundError:
                        pass
                os.fsync(fd)
                raise
