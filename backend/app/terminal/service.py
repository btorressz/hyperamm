from collections import deque
from itertools import count
from datetime import datetime, timezone
from uuid import uuid4
import hashlib
import json
import re
from decimal import Decimal
from .history import TerminalHistory
from .models import (
    TerminalSnapshot,
    TerminalHistoryPoint,
    SystemHealthState,
    SubsystemHealth,
    HealthStatus,
    TerminalEvent,
    EventCategory,
)

EVENT_MAX = 500
CURRENT_EXECUTION_MAX = 100
ACTIVE_ORDER_MAX = 200
_PROCESS_ID = str(uuid4())
_SEQUENCE = count(1)


def safe_text(value):
    """Only normalized messages, with credential-shaped values redacted."""
    text = str(value)
    text = re.sub(
        r"(?i)(api[_-]?key|token|secret|private[_-]?key|authorization)(\s*[:=]\s*)[^\s,;]+",
        r"\1\2[REDACTED]",
        text,
    )
    text = re.sub(r"0x[0-9a-fA-F]{64}\b", "[REDACTED]", text)
    text = re.sub(r"https?://[^\s]+", "[provider URL]", text)
    return text[:500]


def scrub_notices(value, key=None):
    if isinstance(value, dict):
        return {k: scrub_notices(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_notices(v, key) for v in value]
    if isinstance(value, str) and key in {
        "error",
        "message",
        "last_error",
        "reason",
        "reasons",
        "last_reason",
        "manual_kill_reason",
    }:
        return safe_text(value)
    return value


def aggregate_health(data):
    states = {}

    def put(name, status, reason):
        states[name] = SubsystemHealth(status=status, reason=safe_text(reason))

    m, p, refs = data["market"], data["perp_context"], data["references"]
    put(
        "market_feed",
        "DEGRADED" if m["stale"] or m["connection_state"] != "CONNECTED" else "HEALTHY",
        m["connection_state"],
    )
    put(
        "perp_context",
        "UNAVAILABLE" if not p else "DEGRADED" if p["stale"] else "HEALTHY",
        "No evidence" if not p else p["source"],
    )
    evidence = refs["evidence"] if refs else {}
    put(
        "references",
        "UNAVAILABLE"
        if not evidence
        else "DEGRADED"
        if any(not e["healthy"] or e["stale"] for e in evidence.values())
        else "HEALTHY",
        "Individual provider evidence",
    )
    c = data["reference_consensus"]
    put(
        "reference_consensus",
        "UNAVAILABLE"
        if not c
        else "HEALTHY"
        if c["confidence_state"] == "VERIFIED"
        else "DEGRADED",
        c["confidence_state"] if c else "No evidence",
    )
    red = evidence.get("REDSTONE")
    put(
        "redstone_transport",
        "UNAVAILABLE"
        if not red
        else "HEALTHY"
        if red["healthy"] and not red["stale"]
        else "DEGRADED",
        (red.get("transport") or red["status"]) if red else "No evidence",
    )
    agents = data["agents"]
    s = agents.get("supervisor")
    put(
        "agents",
        "UNAVAILABLE"
        if not s
        else "DEGRADED"
        if any(
            (agents.get(k) or {}).get("health") not in ("READY", "DISABLED")
            for k in ("regime", "toxic_flow", "execution_quality")
        )
        else "HEALTHY",
        "Supervisory only" if s else "No decision yet",
    )
    risk = data["risk_firewall"]
    state = risk["state"]
    put(
        "risk",
        "HALTED"
        if risk["manual_kill_active"] or state == "HALT"
        else "HEALTHY"
        if state == "NORMAL"
        else "DEGRADED",
        "Manual kill active" if risk["manual_kill_active"] else state,
    )
    auth = data["risk_authorization"]
    put(
        "final_authorization",
        "HEALTHY" if auth["authorized"] else "HALTED",
        "AUTHORIZED" if auth["authorized"] else "BLOCKED",
    )
    orders = data["orders"]
    mode = data["strategy"]["config"]["execution_mode"]
    put(
        "execution",
        "DEGRADED"
        if any(o["status"] in ("UNKNOWN", "REJECTED") for o in orders)
        else "HEALTHY",
        mode,
    )
    v = data["venue_reconciliation"]
    put(
        "venue_reconciliation",
        "UNAVAILABLE"
        if mode == "PAPER"
        else "DEGRADED"
        if v["error"]
        else "UNAVAILABLE"
        if not v["last_reconciled_at"]
        else "HEALTHY",
        "Not applicable to PAPER"
        if mode == "PAPER"
        else v["error"] or "Venue evidence",
    )
    vault = data["vault"]
    put(
        "accounting",
        "DEGRADED"
        if vault["stale"]
        or vault["error"]
        or vault["accounting_complete"] != "COMPLETE"
        else "HEALTHY",
        vault["accounting_complete"],
    )
    consistency = vault["execution_accounting"]
    put(
        "execution_accounting_consistency",
        "HALTED"
        if consistency["status"] == "DIVERGED"
        else "UNAVAILABLE"
        if consistency["status"] == "UNAVAILABLE"
        else "HEALTHY",
        consistency["status"],
    )
    strategy = data["strategy"]
    put(
        "strategy",
        "DEGRADED"
        if strategy["last_error"]
        else "HALTED"
        if strategy["quote_health"] == "HALTED"
        else "HEALTHY",
        "RUNNING" if strategy["running"] else "STOPPED",
    )
    # PAPER reconciliation is inapplicable; absent required evidence stays visible.
    relevant = [
        v.status
        for k, v in states.items()
        if not (k == "venue_reconciliation" and mode == "PAPER")
    ]
    overall = (
        "HALTED"
        if HealthStatus.HALTED in relevant
        else "DEGRADED"
        if any(x != HealthStatus.HEALTHY for x in relevant)
        else "HEALTHY"
    )
    return SystemHealthState(status=overall, subsystems=states)


class TerminalService:
    """Consumes serialized upstream outputs only. Owns bounded observations."""

    def __init__(self, clock=None):
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.process_id = _PROCESS_ID
        self.session_id = str(uuid4())
        self.sequence = 0
        self.history = TerminalHistory()
        self._events = deque(maxlen=EVENT_MAX)
        self._seen = deque(maxlen=EVENT_MAX * 2)
        self._seen_ids = set()
        self._states = {}
        self._context = None
        self._last_history_at = None
        self._last_emitted_at = None

    def _event(
        self,
        category,
        timestamp,
        message,
        *,
        previous=None,
        state=None,
        reference=None,
        version=None,
        simulated=False,
    ):
        if timestamp.tzinfo is None or timestamp > self._last_emitted_at:
            return
        content = [
            category,
            timestamp.isoformat(),
            message,
            previous,
            state,
            reference,
            version,
        ]
        identity = hashlib.sha256(json.dumps(content, default=str).encode()).hexdigest()
        if identity in self._seen_ids:
            return
        if len(self._seen) == self._seen.maxlen:
            self._seen_ids.discard(self._seen.popleft())
        self._seen.append(identity)
        self._seen_ids.add(identity)
        self._events.append(
            TerminalEvent(
                event_id=identity,
                timestamp=timestamp,
                category=category,
                previous_state=safe_text(previous) if previous is not None else None,
                state=safe_text(state) if state is not None else None,
                message=safe_text(message),
                reference=safe_text(reference) if reference else None,
                version=version,
                simulated=simulated,
            )
        )

    def observe(self, data, diagnostics):
        data = scrub_notices(data)
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("terminal clock must be aware")
        # Wall-clock correction cannot reverse the observation ordering.
        now = max(now, self._last_emitted_at) if self._last_emitted_at else now
        self._last_emitted_at = now
        self.sequence = next(_SEQUENCE)
        config = data["strategy"]["config"]
        context = (
            config["market"],
            config["market_data_mode"],
            config["execution_mode"],
        )
        if context != self._context:
            self.history.clear()
            self._last_history_at = None
            self._events.clear()
            self._seen.clear()
            self._seen_ids.clear()
            self._states.clear()
            self.session_id = str(uuid4())
            self._context = context
        data["strategy_quotes"] = data.get("strategy_quotes", [])
        data["authorized_quotes"] = data["quotes"]
        data["system_health"] = aggregate_health(data)
        all_orders, all_fills = data["orders"], data["fills"]
        totals = data.pop("execution_totals", {})
        counts = {
            state: sum(o["status"] == state for o in all_orders)
            for state in ("OPEN", "PARTIALLY_FILLED", "UNKNOWN", "REJECTED")
        }
        data["execution_summary"] = {
            "order_count": len(all_orders),
            "status_counts": counts,
            "fill_count": totals.get("fill_count", len(all_fills))
            if config["execution_mode"] == "PAPER"
            else None,
            "filled_notional": totals.get("filled_notional", str(
                sum(
                    (Decimal(f["price"]) * Decimal(f["size"]) for f in all_fills),
                    Decimal("0"),
                )
            ))
            if config["execution_mode"] == "PAPER"
            else None,
            "fill_history_available": config["execution_mode"] == "PAPER",
            "recent_limit": CURRENT_EXECUTION_MAX,
            "active_order_limit": ACTIVE_ORDER_MAX,
            "active_orders_truncated": sum(
                o["status"] in ("OPEN", "PARTIALLY_FILLED", "UNKNOWN")
                for o in all_orders
            )
            > ACTIVE_ORDER_MAX,
        }
        active = [
            o
            for o in all_orders
            if o["status"] in ("OPEN", "PARTIALLY_FILLED", "UNKNOWN")
        ]
        data["orders"] = (
            active[-ACTIVE_ORDER_MAX:]
            + [
                o
                for o in all_orders
                if o["status"] not in ("OPEN", "PARTIALLY_FILLED", "UNKNOWN")
            ][-CURRENT_EXECUTION_MAX:]
        )
        data["fills"] = all_fills[-CURRENT_EXECUTION_MAX:]
        data["agent_events"] = data["agent_events"][-20:]
        data["risk_events"] = data["risk_events"][-20:]
        data["accounting"]["events"] = data["accounting"]["events"][-20:]
        data["reconciliation"] = data["reconciliation"][-100:]
        snapshot = TerminalSnapshot.model_validate(
            {
                **data,
                "contract_version": "phase12-v1",
                "process_id": self.process_id,
                "session_id": self.session_id,
                "sequence": self.sequence,
                "emitted_at": now,
                "diagnostics": diagnostics,
            }
        )
        p, inv, v = (
            snapshot.perp_context or {},
            snapshot.inventory or {},
            snapshot.vault,
        )

        def observed(payload):
            timestamp = payload.get("updated_at")
            return (
                timestamp is None
                or datetime.fromisoformat(timestamp.replace("Z", "+00:00")) <= now
            )

        if (
            self._last_history_at is None
            or (now - self._last_history_at).total_seconds() >= 1
        ):
            market_valid = not snapshot.market.stale and (
                snapshot.market.latest_valid_update is None
                or snapshot.market.latest_valid_update <= now
            )
            perp_valid = bool(p) and not p.get("stale", True) and observed(p)
            vault_valid = (
                not v.stale
                and not v.error
                and (v.updated_at is None or v.updated_at <= now)
            )
            quotes = (
                snapshot.authorized_quotes
                if snapshot.risk_authorization["authorized"]
                and observed(
                    {"updated_at": snapshot.risk_authorization.get("created_at")}
                )
                else []
            )
            self.history.append(
                TerminalHistoryPoint(
                    sequence=self.sequence,
                    timestamp=now,
                    mid_price=snapshot.market.mid_price if market_valid else None,
                    fair_value=snapshot.fair_value if market_valid else None,
                    strategy_reference_price=p.get("strategy_reference_price")
                    if perp_valid
                    else None,
                    mark_price=p.get("mark_price") if perp_valid else None,
                    oracle_price=p.get("oracle_price") if perp_valid else None,
                    consensus_price=snapshot.reference_consensus.consensus_price
                    if snapshot.reference_consensus
                    and snapshot.reference_consensus.updated_at <= now
                    else None,
                    best_bid=max(
                        (q.price for q in quotes if q.side == "BID"), default=None
                    ),
                    best_ask=min(
                        (q.price for q in quotes if q.side == "ASK"), default=None
                    ),
                    position_base=inv.get("position_base")
                    if inv and not inv.get("stale") and observed(inv)
                    else None,
                    inventory_ratio=inv.get("inventory_ratio")
                    if inv and not inv.get("stale") and observed(inv)
                    else None,
                    risk_state=snapshot.risk_firewall["state"],
                    agent_regime=(snapshot.agents.get("regime") or {}).get("state"),
                    equity=v.equity_quote if vault_valid else None,
                    peak_equity=v.peak_equity_quote if vault_valid else None,
                    net_pnl=v.net_pnl_quote if vault_valid else None,
                    drawdown_pct=v.drawdown_pct if vault_valid else None,
                    capital_utilization=v.capital_utilization if vault_valid else None,
                    simulated=snapshot.market.simulated,
                    execution_mode=config["execution_mode"],
                )
            )
            self._last_history_at = now
        for category, rows in [
            ("RISK", snapshot.risk_events),
            ("AGENTS", snapshot.agent_events),
            ("ACCOUNTING", snapshot.accounting["events"]),
        ]:
            for event in rows:
                self._event(
                    category,
                    datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")),
                    event.get("message")
                    or "; ".join(event.get("reasons", []))
                    or event.get("category", category),
                    previous=event.get("previous_state"),
                    state=event.get("new_state") or event.get("category"),
                    reference=event.get("source_reference"),
                    version=event.get("risk_version")
                    or event.get("agent_version")
                    or event.get("accounting_version")
                    or event.get("version"),
                    simulated=snapshot.market.simulated,
                )
        transitions = [
            (
                "MARKET",
                "feed",
                snapshot.market.connection_state.value
                + (" STALE" if snapshot.market.stale else " FRESH"),
            ),
            (
                "STRATEGY",
                "strategy",
                ("RUNNING" if snapshot.strategy.running else "STOPPED")
                + (
                    ": " + snapshot.strategy.last_error
                    if snapshot.strategy.last_error
                    else ""
                ),
            ),
            ("SYSTEM", "health", snapshot.system_health.status.value),
        ]
        if snapshot.references:
            transitions += [
                ("REFERENCES", k, e.status.value)
                for k, e in snapshot.references.evidence.items()
            ]
        for order in all_orders[-CURRENT_EXECUTION_MAX:]:
            transitions.append(("EXECUTION", order["client_order_id"], order["status"]))
        signature = hashlib.sha256(
            json.dumps(snapshot.reconciliation, sort_keys=True).encode()
        ).hexdigest()
        if snapshot.reconciliation and signature != self._states.get(
            ("EXECUTION", "reconciliation")
        ):
            actions = ", ".join(
                f"{a['action']} {((a.get('desired') or a.get('existing') or {}).get('side', ''))}"
                for a in snapshot.reconciliation[:12]
            )
            self._event(
                "EXECUTION",
                now,
                "Reconciliation: " + actions,
                reference=signature,
                simulated=snapshot.market.simulated,
            )
        current_states = {("EXECUTION", "reconciliation"): signature}
        for category, key, state in transitions:
            identity = (category, key)
            previous = self._states.get(identity)
            if state != previous:
                self._event(
                    category,
                    now,
                    f"{key}: {state}",
                    previous=previous,
                    state=state,
                    simulated=snapshot.market.simulated,
                )
            current_states[identity] = state
        self._states = current_states  # Bounded by currently retained upstream orders.
        return snapshot

    def events(self, limit=100, category=None):
        if not 1 <= limit <= EVENT_MAX:
            raise ValueError("event limit must be 1..500")
        return sorted(
            (e for e in self._events if category is None or e.category == category),
            key=lambda e: (e.timestamp, e.event_id),
            reverse=True,
        )[:limit]
