"""Export phase12-v1 wire validation from domain models (no runtime dependency).

Run from backend: python scripts/generate_terminal_contract.py
Dictionary-shaped observation wrappers are described here; domain fields come
from their Pydantic serialization schemas. Every serialized field is required,
including nullable fields and defaults. Decimal numbers stay strings on the wire.
"""
import json
from pathlib import Path
from app.terminal.models import TerminalSnapshot
from app.strategy.inventory import InventoryState, InventoryDecision
from app.strategy.market_adaptation import MarketAdaptationDecision
from app.market_data.perp_context import PerpMarketContext, PerpPositionContext
from app.strategy.perp_policy import PerpReferenceDecision
from app.agents.models import AgentEvidenceSnapshot, AgentSupervisorDecision, RegimeAgentOutput, ToxicFlowAgentOutput, ExecutionQualityAgentOutput, AgentEvent
from app.agents.config import AgentConfig
from app.risk.firewall import RiskDecision, RiskFirewallConfig, RiskEvent, ExposureMetrics, PnlDrawdown
from app.risk.authorization import FinalQuoteAuthorization
from app.accounting.models import PnlBreakdown, AccountingNotice, ExecutionAccountingConsistency
from app.accounting.config import AccountingConfig
from app.execution.quote_reconciler import ReconcileAction
from app.references.models import ProviderStatus
from app.agents.models import MarketRegime, ToxicFlowState, ExecutionQualityState
from app.strategy.market_adaptation import VolatilityRegime

STR={"type":"string"}; BOOL={"type":"boolean"}; INT={"type":"integer","minimum":0}; TIME={"type":"string","format":"date-time"}
def nullable(s): return {"anyOf":[s,{"type":"null"}]}
def array(s): return {"type":"array","items":s}
def obj(**props): return {"type":"object","properties":props,"required":list(props),"additionalProperties":False}
def enum(*values): return {"type":"string","enum":list(values)}

def build_contract():
    schema=TerminalSnapshot.model_json_schema(mode="serialization")
    defs=schema['$defs']
    validation=TerminalSnapshot.model_json_schema(mode='validation').get('$defs', {})
    def model(cls):
        valid=cls.model_json_schema(mode='validation')
        validation.update(valid.pop('$defs', {}))
        validation[cls.__name__]=valid
        exported=cls.model_json_schema(mode="serialization")
        defs.update(exported.pop('$defs',{}))
        defs[cls.__name__]=exported
        return {'$ref':f'#/$defs/{cls.__name__}'}
    def properties(cls):
        model(cls)
        return dict(defs[cls.__name__]['properties'])
    inv=properties(InventoryState)
    inv.update({k:nullable(v) for k,v in properties(InventoryDecision).items() if k!='fair_value'})
    perp=properties(PerpMarketContext)
    decision=properties(PerpReferenceDecision)
    for key in ('market_fair_value','funding_score','funding_shift_bps','reference_shift_bps'):
        source='final_reference_shift_bps' if key=='reference_shift_bps' else key
        perp[key]=decision[source] if key=='market_fair_value' else nullable(decision[source])
    perp['strategy_reference_price']=nullable(decision['final_reference_price'])
    perp['position']=nullable(model(PerpPositionContext))
    riskstate=enum('NORMAL','WIDEN','REDUCE','HALT')
    auth= {'anyOf':[model(FinalQuoteAuthorization),obj(authorized={'const':False},risk_state=riskstate,reasons=array(STR))]}
    p=schema['properties']
    p.update(inventory=nullable(obj(**inv)),market_adaptation=nullable(model(MarketAdaptationDecision)),perp_context=nullable(obj(**perp)),
      agents=obj(config=model(AgentConfig),evidence=nullable(model(AgentEvidenceSnapshot)),regime=nullable(model(RegimeAgentOutput)),toxic_flow=nullable(model(ToxicFlowAgentOutput)),execution_quality=nullable(model(ExecutionQualityAgentOutput)),supervisor=nullable(model(AgentSupervisorDecision)),agent_version=INT,agent_fingerprint=STR,telemetry=obj(**{k:INT for k in ('version','fill_observations','reconcile_cycles','tracked_orders','unknown_orders','rejected_orders')})),
      agent_events=array(model(AgentEvent)),risk_firewall=obj(manual_kill_active=BOOL,manual_kill_reason=nullable(STR),config=model(RiskFirewallConfig),state=riskstate,decision=nullable(model(RiskDecision))),risk_authorization=auth,risk_events=array(model(RiskEvent)),projected_exposure=nullable(model(ExposureMetrics)),pnl_drawdown=nullable(model(PnlDrawdown)),
      accounting=obj(config=model(AccountingConfig),accounting_version=INT,accounting_fingerprint=STR,ledger_version=INT,ledger_fingerprint=STR,retention_policy=STR,execution_accounting=model(ExecutionAccountingConsistency),pnl=model(PnlBreakdown),events=array(model(AccountingNotice))),
      reconciliation=array(model(ReconcileAction)),venue_reconciliation=obj(last_reconciled_at=nullable(TIME),error=nullable(STR)),
      diagnostics=obj(testnet_enabled=BOOL,reference_firewall_enabled=BOOL),
      execution_summary=obj(order_count=INT,status_counts={'type':'object','additionalProperties':INT},fill_count=nullable(INT),filled_notional=nullable({'type':'string','format':'decimal'}),fill_history_available=BOOL,recent_limit=INT,active_order_limit=INT,active_orders_truncated=BOOL))
    # String-typed domain enums that predate enum classes.
    for name in ('QuoteLevel','StrategyOrder','Fill'):
        defs[name]['properties']['side']=enum('BID','ASK')
    q=defs['QuoteLevel']['properties']
    q['inventory_intent']=nullable(enum('INVENTORY_INCREASING','INVENTORY_REDUCING','NEUTRAL'))
    q['risk_state']=nullable(riskstate)
    for key,cls in [('agent_regime',RegimeAgentOutput),('agent_toxic_flow_state',ToxicFlowAgentOutput),('agent_execution_quality_state',ExecutionQualityAgentOutput)]:
        q[key]=nullable(defs[cls.__name__]['properties']['state'])
    defs['ReferenceConsensus']['properties']['confidence_state']=enum('VERIFIED','DEGRADED','CONFLICTED','INSUFFICIENT')
    defs['ReferenceConsensus']['properties']['source_statuses']['additionalProperties']=enum(*(x.value for x in ProviderStatus))
    defs['LiquidationEvidence']['properties']['status']=enum('FLAT','UNAVAILABLE','BREACHED','AVAILABLE')
    defs['AgentEvidenceSnapshot']['properties']['reference_confidence']=defs['ReferenceConsensus']['properties']['confidence_state']
    defs['AgentEvidenceSnapshot']['properties']['market_adaptation_regime']=enum(*(x.value for x in VolatilityRegime))
    for cls, name in [(RegimeAgentOutput,'REGIME'),(ToxicFlowAgentOutput,'TOXIC_FLOW'),(ExecutionQualityAgentOutput,'EXECUTION_QUALITY')]:
        defs[cls.__name__]['properties']['agent']={'const':name}
    defs['AgentEvent']['properties']['agent']=enum('REGIME','TOXIC_FLOW','EXECUTION_QUALITY','SUPERVISOR')
    defs['AgentEvent']['properties']['new_state']=enum('MATERIAL_CHANGE',*(x.value for cls in (MarketRegime,ToxicFlowState,ExecutionQualityState) for x in cls))
    defs['AgentEvent']['properties']['previous_state']=nullable(defs['AgentEvent']['properties']['new_state'])
    for name in ('QuoteLevel','StrategyOrder','Fill','PriceEvidence'):
        for key in ('price','size'):
            field=defs[name]['properties'].get(key)
            if field:
                for variant in field.get('anyOf',[field]):
                    if variant.get('type')=='string': variant['exclusiveMinimum']=0
    # Identity, counters and fingerprints have stricter wire semantics than
    # older unconstrained str/int domain declarations.
    def wire_semantics(node, key=None):
        if isinstance(node,list):
            for item in node: wire_semantics(item,key)
        elif isinstance(node,dict):
            if node.get('type')=='integer' and key and (key.endswith('_version') or key in ('version','healthy_sources','healthy_core_sources','healthy_confirmation_count','authorized_quote_count')):
                node['minimum']=max(node.get('minimum',0),0)
            if node.get('type')=='string' and key:
                if key.endswith('fingerprint'): node['format']='sha256'
                elif key in ('market','client_order_id','process_id','session_id'): node['minLength']=1
            for name,value in node.get('properties',{}).items(): wire_semantics(value,name)
            for name in ('anyOf','items','additionalProperties'):
                if name in node: wire_semantics(node[name],key)
    # Shared primitive schema constants must not share mutable nodes across
    # differently named fields (fingerprints, free text, identifiers).
    schema=json.loads(json.dumps(schema))
    defs=schema['$defs']
    wire_semantics(schema)
    for definition in defs.values(): wire_semantics(definition)
    # Pydantic marks serialized Decimal fields with a pattern, but their JSON
    # format must additionally reject numeric values, whitespace and non-finites.
    def normalize(node):
        if isinstance(node,list):
            for item in node: normalize(item)
        elif isinstance(node,dict):
            if node.get('type')=='string' and 'pattern' in node:
                node.pop('pattern'); node['format']='decimal'
            if node.get('type')=='object' and 'properties' in node:
                node['required']=list(node['properties'])
                node['additionalProperties']=False
            for value in list(node.values()): normalize(value)
    def bounds(wire, valid):
        if not isinstance(wire,dict) or not isinstance(valid,dict): return
        if wire.get('type')=='string' and 'pattern' in wire:
            numeric=next((v for v in valid.get('anyOf',[]) if v.get('type')=='number'), {})
            for key in ('minimum','maximum','exclusiveMinimum','exclusiveMaximum'):
                if key in numeric: wire[key]=numeric[key]
        for key, value in wire.get('properties',{}).items():
            bounds(value,valid.get('properties',{}).get(key,{}))
        if 'items' in wire: bounds(wire['items'],valid.get('items',{}))
        for a,b in zip(wire.get('anyOf',[]),valid.get('anyOf',[])): bounds(a,b)
    for name,wire in defs.items(): bounds(wire,validation.get(name,{}))
    normalize(schema)
    return schema

if __name__=='__main__':
    target=Path(__file__).resolve().parents[2]/'frontend/src/contracts/terminal.schema.json'
    target.write_text(json.dumps(build_contract(),indent=2,sort_keys=True)+'\n')
