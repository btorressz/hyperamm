from .models import AccountingEvent, LedgerEntry, fingerprint


class AccountingLedger:
    """Append-only bounded session ledger; HALT_WHEN_FULL is its retention policy.

    Never evict identities or silently lose authoritative history. A full ledger
    requires an internal new research session, not a public reset or overwrite.
    """

    retention_policy = "HALT_WHEN_FULL"

    def __init__(self, *, genesis, max_entries):
        self.genesis_fingerprint = fingerprint(genesis)
        self._fingerprint = self.genesis_fingerprint
        self._entries: list[LedgerEntry] = []
        self._identities: dict[str, str] = {}
        self.max_entries = max_entries

    @property
    def version(self):
        return len(self._entries)

    @property
    def fingerprint(self):
        return self._fingerprint

    def seen(self, event: AccountingEvent):
        previous = self._identities.get(event.event_id)
        if previous is None:
            return False
        if previous != event.fingerprint:
            raise ValueError("conflicting accounting event identity")
        return True

    def append_batch(self, records):
        """Validate the entire fill+fee transaction before committing either row."""
        if all(self.seen(event) for event, _ in records):
            return False
        if any(self.seen(event) for event, _ in records):
            raise ValueError("partial accounting transaction replay")
        if len({event.event_id for event, _ in records}) != len(records):
            raise ValueError("duplicate identity in accounting transaction")
        if self.version + len(records) > self.max_entries:
            raise ValueError("accounting ledger retention capacity exhausted")
        previous = self._fingerprint
        pending = []
        for event, state in records:
            payload = {
                "sequence": self.version + len(pending) + 1,
                **event.model_dump(),
                **state,
                "event_fingerprint": event.fingerprint,
                "previous_ledger_fingerprint": previous,
            }
            # Fingerprint commits to every entry field and post-entry balance.
            previous = fingerprint(payload)
            pending.append(LedgerEntry(**payload, ledger_fingerprint=previous))
        self._entries.extend(pending)
        self._identities.update({event.event_id: event.fingerprint for event, _ in records})
        self._fingerprint = previous
        return True

    def entries(self, limit=100):
        if not 1 <= limit <= 500:
            raise ValueError("ledger limit must be between 1 and 500")
        return tuple(reversed(self._entries[-limit:]))

    def fill_evidence(self):
        """All booked trade identities/economics, independent of API page limits."""
        return {entry.event_id: entry.evidence_fingerprint for entry in self._entries
                if entry.event_type == "TRADE_FILL"}
