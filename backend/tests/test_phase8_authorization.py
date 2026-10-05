from decimal import Decimal as D

from app.amm.models import AmmModel,QuoteLevel
from app.references.models import PriceEvidence,ProviderId,ProviderStatus,ReferenceConsensus,ReferenceSnapshot,SourceType,utcnow
from app.risk.authorization import authorize,fingerprint
from app.risk.firewall import ExposureMetrics,LiquidationEvidence,PnlDrawdown,RiskDecision,RiskState


def quote(price="3000"):
    return QuoteLevel(side="BID",price=D(price),size=D("1"),level_index=0,distance_bps=D("0"),source_model=AmmModel.CONSTANT_PRODUCT)


def snapshot(version=1):
    now=utcnow();e=PriceEvidence(market="ETH",provider=ProviderId.REDSTONE,source_type=SourceType.ORACLE,price=D("3000"),observed_at=now,source_timestamp=now,healthy=True,status=ProviderStatus.HEALTHY,version=version)
    c=ReferenceConsensus(market="ETH",primary_oracle_price=D("3000"),consensus_price=D("3000"),healthy_sources=1,healthy_core_sources=1,confidence_state="DEGRADED",source_statuses={"REDSTONE":"HEALTHY"},version=version,updated_at=now)
    return ReferenceSnapshot(market="ETH",evidence={"REDSTONE":e},consensus=c,deviations_bps={},deviation_magnitudes_bps={},version=version,updated_at=now)


def decision(version=1):
    exp=ExposureMetrics(current_position=D("0"),current_position_notional=D("0"),bid_quote_notional=D("3000"),ask_quote_notional=D("0"),gross_quote_notional=D("3000"),bid_quantity=D("1"),ask_quantity=D("0"),projected_long_base=D("1"),projected_short_base=D("0"),projected_long_notional=D("3000"),projected_short_notional=D("0"),inventory_utilization=D("0"))
    return RiskDecision(state=RiskState.NORMAL,allow_quotes=True,spread_multiplier=D("1"),size_multiplier=D("1"),reasons=["ok"],reference_version=1,market_version=2,inventory_version=3,perp_version=4,projected_long_base=D("1"),projected_short_base=D("0"),exposure=exp,liquidation=LiquidationEvidence(status="FLAT",position_base=D("0"),mark_price=D("3000")),pnl_drawdown=PnlDrawdown(source="TEST"),version=version)


def test_fingerprints_are_deterministic_and_bind_all_versions():
    q=[quote()];r=snapshot();d=decision()
    a1=authorize(q,r,d);a2=authorize(q,r,d)
    assert a1.quote_fingerprint==a2.quote_fingerprint
    assert a1.evidence_fingerprint==a2.evidence_fingerprint
    assert a1.risk_fingerprint==a2.risk_fingerprint
    assert a1.authorization_fingerprint==a2.authorization_fingerprint
    assert len(a1.authorization_fingerprint)==64
    assert a1.market_version==2 and a1.inventory_version==3 and a1.perp_version==4 and a1.reference_version==1 and a1.risk_version==1
    assert authorize([quote("3001")],r,d).quote_fingerprint!=a1.quote_fingerprint
    assert authorize(q,snapshot(2),d).evidence_fingerprint!=a1.evidence_fingerprint
    assert authorize(q,r,decision(2)).risk_fingerprint!=a1.risk_fingerprint


def test_canonical_decimal_and_dict_ordering():
    assert fingerprint({"b":D("1.00"),"a":1})==fingerprint({"a":1,"b":D("1.00")})
