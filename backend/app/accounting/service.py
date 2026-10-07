from collections import deque
from datetime import timezone
from decimal import Decimal

from app.market_data.models import utcnow

from .config import AccountingConfig
from .fees import paper_fee
from .funding import interval_boundary, paper_funding
from .ledger import AccountingLedger
from .models import (AccountingCompleteness, AccountingEvent, AccountingEventType, AccountingNotice,
                     ConsistencyStatus, ExecutionAccountingConsistency,
                     PnlBreakdown, PositionAccounting, VaultSnapshot, fingerprint)
from .pnl import apply_trade, drawdown, mark_position, pnl_breakdown
from .vault import reserved_capital


ZERO = Decimal("0")


class AccountingService:
    """Observe economics only. No order submission, cancellation or venue access."""

    def __init__(self, market, mode="PAPER", config=None, clock=utcnow):
        if mode not in {"PAPER", "TESTNET"}:
            raise ValueError("unsupported accounting mode")
        self.market, self.mode = market, mode
        self.config = config or AccountingConfig()
        self._bound_config = self.config
        self.clock = clock
        self.ledger = AccountingLedger(genesis={"schema": "phase11-v1", "market": market, "mode": mode,
                                                "config": self.config}, max_entries=self.config.ledger_max_entries)
        self._position = PositionAccounting(market=market)
        self._cash = self.config.paper_initial_equity_quote
        self._fees = self._funding = ZERO
        self._peak = self._cash if mode == "PAPER" else None
        self._testnet_initial = None
        self._testnet = {}
        self._reserved = None
        self._updated_at = None
        self._funding_interval = None
        self._last_fill_at = None
        self._fill_inputs = {}
        self.error = None
        self._version = 0
        self._fingerprint = self.ledger.genesis_fingerprint
        self._material = None
        self._events = deque(maxlen=self.config.event_max_entries)
        self._consistency = (ExecutionAccountingConsistency(execution_accounting_consistent=True,
                             status=ConsistencyStatus.CONSISTENT, reason=None)
                             if mode == "PAPER" else ExecutionAccountingConsistency())
        self._publish()

    @property
    def version(self):
        return self._version

    @property
    def fingerprint(self):
        return self._fingerprint

    @property
    def position(self):
        return self._position

    def _publish(self):
        state = {"genesis": self.ledger.genesis_fingerprint, "ledger": self.ledger.fingerprint,
                 "position": self._position, "cash": self._cash if self.mode == "PAPER" else None,
                 "fees": self._fees if self.mode == "PAPER" else None,
                 "funding": self._funding if self.mode == "PAPER" else None,
                 "peak": self._peak, "reservation": self._reserved, "error": self.error,
                 "execution_accounting": self._consistency,
                 "testnet": self._testnet, "testnet_initial": self._testnet_initial}
        material = fingerprint(state)
        if material != self._material:
            self._version += 1
            self._material = material
            self._fingerprint = fingerprint({"version": self._version, "state": material})

    def _notice(self, category, message, reference=None, timestamp=None):
        self._events.append(AccountingNotice(timestamp=timestamp or self.clock(), category=category,
                            message=message, source_reference=reference, accounting_version=self.version))

    def fail(self, message):
        # Preserve the first failure; repeated require/refresh calls cannot mask
        # fatal evidence or churn authority by wrapping the same error again.
        if self.error is None:
            self.error = str(message)
            self._publish()
            self._notice("ACCOUNTING_ERROR", self.error)

    def _require_paper(self):
        if self.config != self._bound_config:
            raise ValueError("accounting configuration mismatch; new internal PAPER session required")
        if not self.config.enabled:
            raise ValueError("accounting is disabled; capital authority unavailable")
        if self.mode != "PAPER":
            raise ValueError("TESTNET full fill accounting is unavailable")
        if self.error:
            raise ValueError(f"accounting error: {self.error}")

    @staticmethod
    def _balances(position, cash, fees, funding):
        return {"cash_balance_quote": cash, "position_base": position.position_base,
                "average_entry_price": position.average_entry_price,
                "cumulative_realized_pnl": position.realized_pnl_quote,
                "cumulative_fees": fees, "cumulative_funding": funding}

    def _observe_equity(self):
        """Observe only the committed, fee-adjusted PAPER economic state."""
        if self.mode != "PAPER":
            return False
        pnl = self.pnl()
        if pnl.net_pnl is None:
            return False
        equity = self.config.paper_initial_equity_quote + pnl.net_pnl
        if self._peak is None or equity > self._peak:
            self._peak = equity
            return True
        return False

    @staticmethod
    def fill_identity(fill):
        return fingerprint({"client_order_id": fill.client_order_id, "market": fill.market,
                            "timestamp": fill.timestamp, "source": fill.source})

    def _fill_evidence(self, fill):
        identity = self.fill_identity(fill)
        fee = paper_fee(fill, identity, self.config)
        return identity, fee, fingerprint({"fill": fill, "fee": fee})

    def observe_execution_fills(self, fills, *, retired_count=0, duplicate_fills=()):
        """Compare current-session execution against actual immutable trade rows.

        Detection only: never replay or clear a latched accounting failure.
        Standalone research users supply their execution evidence explicitly.
        """
        if self.mode != "PAPER":
            return self._consistency
        booked = self.ledger.fill_evidence()
        seen, missing, conflicts = set(), [], []
        accounted = 0
        duplicate_objects = {id(fill) for fill in duplicate_fills}
        for fill in fills:
            identity, _, economics = self._fill_evidence(fill)
            trade_id = "fill:" + identity
            if id(fill) in duplicate_objects:
                conflicts.append("duplicate execution fill identity after consumption")
                missing.append(fill)
            elif identity in seen:
                conflicts.append("duplicate execution fill identity")
                missing.append(fill)
            elif fill.market != self.market:
                conflicts.append("execution fill market mismatch")
                missing.append(fill)
            elif trade_id not in booked:
                missing.append(fill)
            elif booked[trade_id] != economics:
                conflicts.append("conflicting execution/accounting fill economics")
                missing.append(fill)
            else:
                accounted += 1
            seen.add(identity)
        reason = "; ".join(sorted(set(conflicts))) if conflicts else (
            f"{len(missing)} executed PAPER fill(s) not represented in accounting ledger" if missing else None)
        previous = self._consistency
        self._consistency = ExecutionAccountingConsistency(
            execution_fill_count=len(fills)+retired_count, accounted_fill_count=accounted+retired_count,
            unaccounted_fill_count=len(missing), execution_accounting_consistent=not missing,
            oldest_unaccounted_fill_at=min((f.timestamp for f in missing), default=None),
            latest_unaccounted_fill_at=max((f.timestamp for f in missing), default=None),
            status=ConsistencyStatus.DIVERGED if missing else ConsistencyStatus.CONSISTENT, reason=reason)
        self._publish()
        if previous.status != self._consistency.status:
            self._notice("EXECUTION_ACCOUNTING_" + self._consistency.status,
                         reason or "All executed PAPER fills represented in accounting ledger")
        if conflicts:
            self.fail(reason)
        return self._consistency

    def reconcile_paper_fills(self, fills):
        """Internal pending-evidence booking; never recover a latched failure.

        Replay is allowed only before newer mark/funding evidence. Each fill
        still passes the ordinary economics, chronology and atomic capacity
        checks. Stop at the first failure and retain every unbooked identity.
        """
        self.observe_execution_fills(fills)
        if self.mode != "PAPER" or self.error:
            return self._consistency
        booked = self.ledger.fill_evidence()
        try:
            self._require_paper()
            for fill in fills:
                if "fill:" + self.fill_identity(fill) in booked:
                    continue
                if any(fill.timestamp < timestamp for timestamp in
                       (self._updated_at, self._funding_interval) if timestamp is not None):
                    raise ValueError("pending fill predates irreversible mark/funding evidence; new PAPER session required")
                self.ingest_fill(fill)
        except Exception as exc:
            self.fail(exc)
        finally:
            self.observe_execution_fills(fills)
        return self._consistency

    def ingest_fill(self, fill):
        try:
            return self._ingest_fill(fill)
        except Exception as exc:
            self.fail(exc)
            raise

    def _ingest_fill(self, fill):
        self._require_paper()
        if fill.market != self.market:
            raise ValueError("accounting fill market mismatch")
        if fill.timestamp.tzinfo is None:
            raise ValueError("accounting fill timestamp must be timezone-aware")
        identity, fee, economics = self._fill_evidence(fill)
        # Check input economics before computing realized deltas against current state.
        trade_id = "fill:" + identity
        if identity in self._fill_inputs:
            if self._fill_inputs[identity] != economics:
                raise ValueError("conflicting fill replay economics")
            self._notice("FILL_DUPLICATE_IGNORED", "Economic event already booked", trade_id, fill.timestamp)
            return False
        if self._last_fill_at is not None and fill.timestamp < self._last_fill_at:
            raise ValueError("out-of-order accounting fill")
        position, realized = apply_trade(self._position, side=fill.side, price=fill.price, size=fill.size)
        trade = AccountingEvent(event_id=trade_id, event_type=AccountingEventType.TRADE_FILL,
                    market=self.market, timestamp=fill.timestamp, source=fill.source, simulated=True,
                    source_reference=fill.client_order_id, cash_delta_quote=realized,
                    position_delta_base=fill.size if fill.side == "BID" else -fill.size,
                    realized_pnl_delta=realized, side=fill.side, price=fill.price, size=fill.size,
                    evidence_fingerprint=economics)
        fee_event = AccountingEvent(event_id="fee:" + identity, event_type=AccountingEventType.FEE,
                    market=self.market, timestamp=fill.timestamp, source="PAPER_CONFIG", simulated=True,
                    source_reference=trade_id, cash_delta_quote=-fee.fee_quote,
                    fee_delta_quote=fee.fee_quote, evidence_fingerprint=fee.fingerprint)
        cash = self._cash + realized
        self.ledger.append_batch([
            (trade, self._balances(position, cash, self._fees, self._funding)),
            (fee_event, self._balances(position, cash - fee.fee_quote, self._fees + fee.fee_quote, self._funding)),
        ])
        self._fill_inputs[identity] = economics
        previous = self._position.position_base
        self._position, self._cash = position, cash - fee.fee_quote
        self._fees += fee.fee_quote
        self._last_fill_at = fill.timestamp
        peak_changed = self._observe_equity()
        self._publish()
        if peak_changed:
            self._notice("EQUITY_PEAK_UPDATED", "Research equity high-water mark updated", trade_id, fill.timestamp)
        self._notice("FILL_BOOKED", "Simulated trade accounted", trade_id, fill.timestamp)
        self._notice("FEE_BOOKED", "PAPER_CONFIG research fee", fee_event.event_id, fill.timestamp)
        new = position.position_base
        category = ("POSITION_OPENED" if previous == 0 else "POSITION_CLOSED" if new == 0
                    else "POSITION_REVERSED" if (previous > 0) != (new > 0)
                    else "POSITION_REDUCED" if abs(new) < abs(previous) else None)
        if category:
            self._notice(category, "Average-cost position updated", trade_id, fill.timestamp)
        return True

    def accrue_funding(self, *, effective_at, mark, rate, evidence_version=0):
        try:
            self._require_paper()
            if not self.config.paper_funding_accounting_enabled:
                return False
            if interval_boundary(effective_at, self.config.paper_funding_interval_seconds) != effective_at:
                raise ValueError("funding effective time must be an explicit interval boundary")
            effective_at = effective_at.astimezone(timezone.utc)
            accrual = paper_funding(market=self.market, effective_at=effective_at,
                         position=self._position.position_base, mark=mark, rate=rate, evidence_version=evidence_version)
            event = AccountingEvent(event_id=f"funding:{self.market}:{effective_at.isoformat()}",
                       event_type=AccountingEventType.FUNDING, market=self.market, timestamp=effective_at,
                       source=accrual.source, simulated=True, source_reference=str(evidence_version),
                       cash_delta_quote=accrual.funding_delta_quote, funding_delta_quote=accrual.funding_delta_quote,
                       evidence_fingerprint=accrual.fingerprint)
            if self.ledger.seen(event):
                return False
            if self._funding_interval is not None and effective_at <= self._funding_interval:
                raise ValueError("out-of-order funding interval")
            cash, funding = self._cash + accrual.funding_delta_quote, self._funding + accrual.funding_delta_quote
            self.ledger.append_batch([(event, self._balances(self._position, cash, self._fees, funding))])
            self._cash, self._funding = cash, funding
            self._funding_interval = effective_at
            peak_changed = self._observe_equity()
            self._publish()
            if peak_changed:
                self._notice("EQUITY_PEAK_UPDATED", "Research equity high-water mark updated", event.event_id, effective_at)
            self._notice("FUNDING_BOOKED", "Deterministic PAPER research interval", event.event_id, effective_at)
            return True
        except Exception as exc:
            self.fail(exc)
            raise

    def observe_funding(self, context):
        if not self.config.paper_funding_accounting_enabled or self.mode != "PAPER":
            return
        boundary = interval_boundary(context.updated_at, self.config.paper_funding_interval_seconds)
        if self._funding_interval is None:
            self._funding_interval = boundary
        elif boundary > self._funding_interval:
            if (boundary - self._funding_interval).total_seconds() != self.config.paper_funding_interval_seconds:
                self.fail("funding interval gap; historical basis unavailable")
                raise ValueError(self.error)
            self.accrue_funding(effective_at=boundary, mark=context.mark_price, rate=context.funding_rate,
                                evidence_version=context.version)

    def mark(self, mark, *, observed_at=None):
        try:
            self._require_paper()
            position = mark_position(self._position, mark)
            timestamp = observed_at or self.clock()
            if timestamp.tzinfo is None:
                raise ValueError("accounting mark timestamp must be timezone-aware")
            if self._updated_at is not None and timestamp < self._updated_at:
                raise ValueError("out-of-order accounting mark")
            self._position, self._updated_at = position, timestamp
            peak_changed = self._observe_equity()
            self._publish()
            if peak_changed:
                self._notice("EQUITY_PEAK_UPDATED", "Research equity high-water mark updated", timestamp=timestamp)
        except Exception as exc:
            self.fail(exc)
            raise

    def reserve(self, desired=(), existing=()):
        try:
            self._require_paper()
            if self._position.mark_price is None:
                raise ValueError("reservation mark unavailable")
            self._reserved = reserved_capital(self._position.position_base, self._position.mark_price, desired, existing)
            self._publish()
            return self._reserved
        except Exception as exc:
            self.fail(exc)
            raise

    def reservation_snapshot(self, desired=(), existing=()):
        """Evaluate proposed risk without publishing transient candidate authority."""
        vault = self.snapshot()
        if vault.position_base is None or vault.mark_price is None or vault.equity_quote is None:
            return vault
        reserved = reserved_capital(vault.position_base, vault.mark_price, desired, existing)
        return vault.model_copy(update={
            "reserved_capital_quote": reserved,
            "available_capital_quote": max(ZERO, vault.equity_quote - reserved),
            "capital_utilization": reserved / vault.equity_quote if vault.equity_quote > 0 else None,
        })

    def observe_testnet(self, position, account, *, mark=None):
        if self.mode != "TESTNET":
            raise ValueError("TESTNET evidence cannot enter PAPER accounting")
        if position is not None and (position.market != self.market or position.source != "TESTNET"):
            self.fail("invalid TESTNET position provenance")
            raise ValueError(self.error)
        evidence = {
            "position": position.model_dump(exclude={"updated_at", "stale"}) if position is not None else None,
            "account_value": account.get("account_value") if account else None,
            "total_margin_used": account.get("total_margin_used") if account else None,
            "withdrawable": account.get("withdrawable") if account else None,
            "mark": mark,
        }
        financial = [evidence["account_value"], evidence["total_margin_used"], evidence["withdrawable"], mark]
        if position is not None:
            financial.extend(value for value in position.model_dump().values() if isinstance(value, Decimal))
        for value in financial:
            if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):
                self.fail("invalid TESTNET accounting evidence")
                raise ValueError(self.error)
        self._testnet = evidence
        equity = self._testnet["account_value"]
        if equity is not None:
            if self._testnet_initial is None:
                self._testnet_initial = equity
            self._peak = max(self._peak, equity) if self._peak is not None else equity
        times = [v for v in (position.updated_at if position else None, account.get("updated_at") if account else None) if v]
        self._updated_at = min(times) if times else None
        if position is not None and position.stale:
            self._updated_at = None
        self._publish()

    def pnl(self):
        if self.mode == "PAPER":
            return pnl_breakdown(self._position, self._fees, self._funding)
        position = self._testnet.get("position") or {}
        equity = self._testnet.get("account_value")
        return PnlBreakdown(unrealized_trading_pnl=position.get("unrealized_pnl"),
                            session_pnl=equity - self._testnet_initial if equity is not None else None)

    def snapshot(self, *, now=None):
        now = now or self.clock()
        age = (now - self._updated_at).total_seconds() if self._updated_at else None
        stale = age is None or age < 0 or age > self.config.accounting_stale_after_seconds
        common = dict(mode=self.mode, market=self.market, simulated=self.mode == "PAPER",
                      ledger_version=self.ledger.version, ledger_fingerprint=self.ledger.fingerprint,
                      accounting_version=self.version, accounting_fingerprint=self.fingerprint,
                      updated_at=self._updated_at, stale=stale, error=self.error)
        common["execution_accounting"] = self._consistency
        if self.mode == "TESTNET":
            pos = self._testnet.get("position") or {}
            equity = self._testnet.get("account_value")
            amount, pct = drawdown(equity, self._peak)
            return VaultSnapshot(**common, source="TESTNET_AUTHORITATIVE_USER_STATE",
                accounting_complete=AccountingCompleteness.PARTIAL if pos or equity is not None else AccountingCompleteness.UNAVAILABLE,
                position_base=pos.get("signed_position_base"), average_entry_price=pos.get("entry_price"),
                position_value_quote=pos.get("position_value"), mark_price=self._testnet.get("mark"),
                unrealized_pnl_quote=pos.get("unrealized_pnl"), equity_quote=equity,
                peak_equity_quote=self._peak, drawdown_quote=amount, drawdown_pct=pct,
                margin_used_quote=self._testnet.get("total_margin_used"),
                position_margin_used_quote=pos.get("margin_used"),
                venue_withdrawable_quote=self._testnet.get("withdrawable"),
                liquidation_price=pos.get("liquidation_price"), return_on_equity=pos.get("return_on_equity"),
                session_pnl_quote=self.pnl().session_pnl,
                warnings=("PARTIAL: complete normalized TESTNET fill ledger unavailable.",
                          "Cash, realized PnL, fees, funding payments and available trading capital unavailable.",
                          "Account equity is account-wide; position evidence is market-specific."))
        pnl = self.pnl()
        equity = self.config.paper_initial_equity_quote + pnl.net_pnl if pnl.net_pnl is not None else None
        amount, pct = drawdown(equity, self._peak)
        available = max(ZERO, equity - self._reserved) if equity is not None and self._reserved is not None else None
        utilization = self._reserved / equity if equity is not None and equity > 0 and self._reserved is not None else None
        warnings = ["PAPER / SIMULATED perpetual research accounting; settled capital is research capital.",
                    "SIMULATED CAPITAL RESERVATION: full notional; not exchange margin."]
        if not self.config.paper_fee_model_enabled:
            warnings.append("Configured zero-fee research accounting (PAPER_CONFIG).")
        if not self.config.paper_funding_accounting_enabled:
            warnings.append("Configured zero-funding research accounting.")
        if not self.config.enabled:
            warnings.append("Accounting disabled; new capital authority unavailable.")
        return VaultSnapshot(**common, source="PAPER_RESEARCH", accounting_complete=
            AccountingCompleteness.COMPLETE if equity is not None and not stale and not self.error and self.config.enabled
            and self._consistency.execution_accounting_consistent is True
            else AccountingCompleteness.UNAVAILABLE,
            initial_equity_quote=self.config.paper_initial_equity_quote, settled_capital_quote=self._cash,
            position_base=self._position.position_base, average_entry_price=self._position.average_entry_price,
            mark_price=self._position.mark_price, position_value_quote=self._position.position_value_quote,
            realized_pnl_quote=pnl.realized_trading_pnl, unrealized_pnl_quote=pnl.unrealized_trading_pnl,
            gross_pnl_quote=pnl.gross_trading_pnl, fees_quote=self._fees, funding_quote=self._funding,
            net_pnl_quote=pnl.net_pnl, session_pnl_quote=pnl.session_pnl, equity_quote=equity,
            peak_equity_quote=self._peak, drawdown_quote=amount, drawdown_pct=pct,
            reserved_capital_quote=self._reserved, available_capital_quote=available,
            gross_exposure_quote=abs(self._position.position_value_quote) if self._position.position_value_quote is not None else None,
            net_exposure_quote=self._position.position_value_quote, capital_utilization=utilization,
            fee_source="PAPER_CONFIG", funding_source="PAPER_RESEARCH_INTERVAL" if self.config.paper_funding_accounting_enabled else "PAPER_CONFIG",
            reservation_source="SIMULATED_CAPITAL_RESERVATION", warnings=tuple(warnings))

    def require_fresh(self):
        vault = self.snapshot()
        if not self.config.enabled or vault.stale or vault.error or vault.accounting_complete == AccountingCompleteness.UNAVAILABLE:
            raise RuntimeError("accounting stale, error or unavailable; recompute before transmission")
        return vault

    def events(self, limit=100):
        if not 1 <= limit <= 500:
            raise ValueError("accounting event limit must be between 1 and 500")
        return tuple(list(self._events)[-limit:])
