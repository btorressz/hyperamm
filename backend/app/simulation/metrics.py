from __future__ import annotations

from collections import Counter
from decimal import Decimal

from app.agents.execution_quality import churn_ratio,spread_capture_bps
from .models import SimulationMetrics


class MetricsAccumulator:
    def __init__(self,initial_equity:Decimal):
        self.initial_equity=initial_equity
        self.peak_equity=initial_equity
        self.max_drawdown_pct=Decimal("0")
        self.max_abs_inventory=Decimal("0")
        self.max_inventory_utilization=Decimal("0")
        self.quoted_notional=Decimal("0")
        self.keep=self.create=self.replace=self.cancel=0
        self.risk=Counter()
        self.regime=Counter()
        self.toxic=Counter()
        self.execution=Counter()

    def record(
        self,*,authorized_quotes,inventory,risk_decision,agent_decision,equity:Decimal,drawdown_pct:Decimal,actions
    ):
        self.peak_equity=max(self.peak_equity,equity)
        self.max_drawdown_pct=max(self.max_drawdown_pct,drawdown_pct)
        self.max_abs_inventory=max(self.max_abs_inventory,abs(inventory.position_base))
        self.max_inventory_utilization=max(self.max_inventory_utilization,risk_decision.exposure.inventory_utilization)
        self.quoted_notional+=sum((q.price*q.size for q in authorized_quotes),Decimal("0"))
        for action in actions:
            value=action.action.value
            if value=="KEEP":self.keep+=1
            elif value=="CREATE":self.create+=1
            elif value=="REPLACE":self.replace+=1
            elif value=="CANCEL":self.cancel+=1
        self.risk[risk_decision.state.value]+=1
        self.regime[agent_decision.regime.state.value]+=1
        self.toxic[agent_decision.toxic_flow.state.value]+=1
        self.execution[agent_decision.execution_quality.state.value]+=1

    def finalize(self,*,paper,market:str,vault,telemetry,history,agent_config,frame_count:int)->SimulationMetrics:
        fills=paper.fills.all()
        session=vault.net_pnl_quote
        ending=vault.equity_quote
        buy=sum(1 for f in fills if f.side=="BID")
        sell=sum(1 for f in fills if f.side=="ASK")
        filled_notional=sum((f.price*f.size for f in fills),Decimal("0"))
        activity=filled_notional/self.quoted_notional if self.quoted_notional>0 else None

        observed=telemetry.fills(agent_config.execution_quality_window)
        captures=[
            spread_capture_bps(f.side,f.price,f.reference_price)
            for f in observed if f.reference_price is not None
        ]
        mean_capture=sum(captures,Decimal("0"))/Decimal(len(captures)) if captures else None
        markouts,_=telemetry.markouts(
            history,horizon_seconds=agent_config.toxic_flow_markout_horizon_seconds,
            window=agent_config.toxic_flow_window_fills,
        )
        mean_markout=sum((m.signed_markout_bps for m in markouts),Decimal("0"))/Decimal(len(markouts)) if markouts else None
        adverse=sum(1 for m in markouts if m.signed_markout_bps<0)
        adverse_rate=Decimal(adverse)/Decimal(len(markouts)) if markouts else None
        churn=churn_ratio(self.keep,self.create,self.replace,self.cancel)

        return SimulationMetrics(
            frame_count=frame_count,starting_equity=self.initial_equity,ending_equity=ending,
            session_pnl=session,return_pct=session/self.initial_equity*Decimal("100"),
            realized_pnl=vault.realized_pnl_quote,unrealized_pnl=vault.unrealized_pnl_quote,
            max_drawdown_pct=self.max_drawdown_pct,fill_count=len(fills),buy_fill_count=buy,sell_fill_count=sell,
            quoted_notional=self.quoted_notional,filled_notional=filled_notional,fill_activity_ratio=activity,
            ending_inventory_base=vault.position_base,max_abs_inventory_base=self.max_abs_inventory,
            max_inventory_utilization=self.max_inventory_utilization,mean_spread_capture_bps=mean_capture,
            mean_mature_markout_bps=mean_markout,adverse_fill_rate=adverse_rate,
            keep_count=self.keep,create_count=self.create,replace_count=self.replace,cancel_count=self.cancel,
            reconciliation_churn_ratio=churn,risk_state_counts=dict(self.risk),
            risk_halt_fraction=Decimal(self.risk.get("HALT",0))/Decimal(frame_count),
            agent_regime_counts=dict(self.regime),toxic_flow_state_counts=dict(self.toxic),
            execution_quality_state_counts=dict(self.execution),
        )
