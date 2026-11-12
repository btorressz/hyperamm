import pytest

from app.portfolio_research.models import PortfolioStressRequest,PortfolioStressResult
from app.simulation.models import stable_fingerprint
from app.simulation.service import SimulationService
from phase174_fixtures import request_for,selloff174,concentration174
from phase173_fixtures import reseal


async def test_repeatability_and_input_order_bind_result(selloff174):
    r=await SimulationService().stress_portfolio_research(request=request_for(markets=("SOL","ETH","BTC")))
    assert r==selloff174

@pytest.mark.parametrize("field",["magnitude","duration","onset","transmission","execution"])
def test_changes_bind_scenario_request_and_dataset_identity(field):
    from app.portfolio_research.stress import prepared_datasets
    r=request_for("BTC_LED_VOLATILITY")
    raw=r.model_dump()
    if field=="magnitude": raw["scenario"]["assumptions"]["btc_decline_fraction"]="0.061"
    elif field=="duration": raw["scenario"]["duration_frames"]-=1
    elif field=="onset": raw["scenario"]["onset_frame"]-=1
    elif field=="transmission": raw["scenario"]["assumptions"]["eth_transmission"]="1.6"
    else:
        from app.research_replay.comparison import ComparisonConfigSnapshot
        for s in raw["config"]["scenarios"]:
            i=ComparisonConfigSnapshot.model_validate(s["captured"]).inputs().model_dump(mode="json")
            i["simulation"]["execution"].update(mode="MODELED_CROSSING",slippage_bps="1")
            from app.simulation.config import SimulationConfig
            i["simulation"]=SimulationConfig.model_validate(i["simulation"]).model_dump(mode="json")
            s["captured"]=ComparisonConfigSnapshot.from_payload(i)
        from app.portfolio_research.models import PortfolioResearchConfig
        raw["config"]=PortfolioResearchConfig.model_validate(raw["config"])
        raw["config_fingerprint"]=raw["config"].fingerprint()
    changed=PortfolioStressRequest.model_validate(raw)
    assert stable_fingerprint(changed)!=stable_fingerprint(r)
    if field!="execution":
        assert changed.scenario.fingerprint()!=r.scenario.fingerprint()
        assert prepared_datasets(r,None)[1]["ETH"].fingerprint!=prepared_datasets(changed,None)[1]["ETH"].fingerprint

@pytest.mark.parametrize("field",["dataset","result","metrics","transition","scenario","baseline","selection"])
def test_resealed_tampering_still_rejected(selloff174,field):
    r=selloff174
    raw={n:getattr(r,n) for n in type(r).model_fields if n!="evidence_fingerprint"}
    if field in {"dataset","result"}:
        markets=list(r.markets)
        markets[0]=markets[0].model_copy(update={"stressed_dataset_fingerprint" if field=="dataset" else "stressed_result_fingerprint":"f"*64})
        raw["markets"]=tuple(markets)
    elif field=="metrics":
        metrics=list(r.metrics.comparisons);metrics[0]=metrics[0].model_copy(update={"difference":"1"})
        raw["metrics"]=r.metrics.model_copy(update={"comparisons":tuple(metrics)})
    elif field=="transition":raw["risk_transition"]=r.risk_transition.model_copy(update={"transition":"NORMAL -> HALT"})
    elif field=="scenario":raw["scenario_fingerprint"]="f"*64
    elif field=="baseline":raw["baseline"]=r.stressed
    else:raw["concentration_selection"]={"market":"BTC","sequence":1,"candidates":[],"candidate_markets":[],"native_evidence_fingerprints":[]}
    from app.portfolio_research.models import sealed
    with pytest.raises(ValueError): sealed(PortfolioStressResult,**raw)


def test_user_receipts_and_forged_assumptions_cannot_enter_request():
    r=request_for();raw=r.model_dump();raw["baseline"]={"authoritative":True}
    with pytest.raises(ValueError): PortfolioStressRequest.model_validate(raw)
    forged=r.model_copy(update={"scenario":r.scenario.model_copy(update={"duration_frames":9999})})
    with pytest.raises(ValueError): PortfolioStressRequest.model_validate(forged)


@pytest.mark.parametrize("field,value",[("position_base","0.000000001"),("mark_price_quote","0.000000001"),("equity_quote","1")])
def test_concentration_candidate_financial_substitution_is_rejected(concentration174,field,value):
    selection=concentration174.concentration_selection
    candidates=list(selection.candidates)
    candidates[0]=candidates[0].model_copy(update={field:value})
    selection=selection.model_copy(update={"candidates":tuple(candidates)})
    with pytest.raises(ValueError):
        reseal(concentration174,concentration_selection=selection)
