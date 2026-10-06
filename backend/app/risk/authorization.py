from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel,Field
from app.market_data.models import utcnow
from .firewall import RiskDecision,RiskState

def _canonical(value):
    if isinstance(value,Decimal):return format(value,"f")
    if isinstance(value,datetime):return value.astimezone(timezone.utc).isoformat()
    if isinstance(value,Enum):return value.value
    if hasattr(value,"model_dump"):return _canonical(value.model_dump())
    if isinstance(value,dict):return {str(k):_canonical(v) for k,v in sorted(value.items(),key=lambda x:str(x[0]))}
    if isinstance(value,(list,tuple)):return [_canonical(v) for v in value]
    return value
def fingerprint(value):
    raw=json.dumps(_canonical(value),sort_keys=True,separators=(",",":"),ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()

class FinalQuoteAuthorization(BaseModel):
    authorized:bool
    risk_state:RiskState
    quote_fingerprint:str
    evidence_fingerprint:str
    risk_fingerprint:str
    authorization_fingerprint:str
    market_version:int
    inventory_version:int
    perp_version:int
    reference_version:int
    agent_version:int=0
    agent_fingerprint:str
    risk_version:int
    authorized_quote_count:int
    bid_authorized:bool
    ask_authorized:bool
    reasons:list[str]
    created_at:datetime=Field(default_factory=utcnow)

def authorize(quotes,refs,decision:RiskDecision,agent=None):
    qf=fingerprint(quotes);ef=fingerprint(refs);rf=fingerprint(decision)
    agent_version=agent.version if agent is not None else 0
    agent_fingerprint=agent.fingerprint if agent is not None else fingerprint({"phase9":"not-bound"})
    payload={"quote_fingerprint":qf,"evidence_fingerprint":ef,"risk_fingerprint":rf,"agent_fingerprint":agent_fingerprint,"market_version":decision.market_version,"inventory_version":decision.inventory_version,"perp_version":decision.perp_version,"reference_version":decision.reference_version,"agent_version":agent_version,"risk_version":decision.version}
    return FinalQuoteAuthorization(authorized=decision.allow_quotes,risk_state=decision.state,quote_fingerprint=qf,evidence_fingerprint=ef,risk_fingerprint=rf,authorization_fingerprint=fingerprint(payload),market_version=decision.market_version,inventory_version=decision.inventory_version,perp_version=decision.perp_version,reference_version=decision.reference_version,agent_version=agent_version,agent_fingerprint=agent_fingerprint,risk_version=decision.version,authorized_quote_count=len(quotes),bid_authorized=any(q.side=="BID" for q in quotes),ask_authorized=any(q.side=="ASK" for q in quotes),reasons=decision.reasons)
