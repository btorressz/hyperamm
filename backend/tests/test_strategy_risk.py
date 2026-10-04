from decimal import Decimal as D
from datetime import timedelta
import pytest
from pydantic import ValidationError
from app.strategy.models import StrategyConfig
from app.strategy.fair_value import calculate_fair_value
from app.strategy.quote_engine import QuoteEngine
from app.market_data.mock import MockMarketDataAdapter
from app.risk.models import RiskStatus
from app.risk.limits import validate_quotes
from app.risk.kill_switch import KillSwitch
from app.execution.paper import PaperExecutionAdapter
from app.execution.models import OrderRequest
from app.market_data.models import utcnow


def test_strategy_config_validation():
    with pytest.raises(ValidationError): StrategyConfig(levels_per_side=0)
    with pytest.raises(ValidationError): StrategyConfig(concentration_lower_bps=D('100'),concentration_upper_bps=D('10'))

def test_market_data_freshness_rejection():
    snap=MockMarketDataAdapter().snapshot_for(1); snap.stale=True
    with pytest.raises(ValueError): calculate_fair_value(snap)

def test_quote_engine_and_risk_limits():
    snap=MockMarketDataAdapter().snapshot_for(1)
    fair,pool,quotes=QuoteEngine().generate(StrategyConfig(),snap)
    validate_quotes(quotes,snap,RiskStatus())
    assert fair==snap.mid_price and len(quotes)==16

@pytest.mark.asyncio
async def test_kill_switch_cancels_and_prevents_quotes():
    ex=PaperExecutionAdapter(); snap=MockMarketDataAdapter().snapshot_for(1); ex.update_market(snap)
    await ex.submit_orders([OrderRequest(client_order_id='x',market='ETH',side='BID',price=snap.best_bid-D('10'),size=D('1'))])
    risk=RiskStatus(); kill=KillSwitch(risk); await kill.activate(ex,'test')
    assert risk.kill_switch_active and not await ex.get_open_orders()
    with pytest.raises(PermissionError): validate_quotes([],snap,risk)

def test_execution_authority_requires_running():
    from app.risk.limits import validate_execution_authority
    risk=RiskStatus()
    with pytest.raises(PermissionError):
        validate_execution_authority(risk=risk,execution_mode='PAPER',strategy_running=False)
    validate_execution_authority(risk=risk,execution_mode='PAPER',strategy_running=True)


def test_env_example_matches_settings_and_safe_defaults():
    from pathlib import Path
    from dotenv import dotenv_values
    from app.config import Settings
    values=dotenv_values(Path(__file__).resolve().parents[2]/'.env.example')
    assert all(name.lower() in Settings.model_fields for name in values)
    settings=Settings(_env_file=None,**{name.lower():value for name,value in values.items()})
    assert settings.execution_mode=='PAPER' and settings.market_data_mode=='DEMO'
    assert not settings.enable_hyperliquid_testnet_orders and not settings.hyperliquid_private_key


@pytest.mark.parametrize('field,value',[('price','NaN'),('size','Infinity'),('size','0')])
def test_risk_rejects_mutated_invalid_quote(field,value):
    snap=MockMarketDataAdapter().snapshot_for(1)
    _,_,quotes=QuoteEngine().generate(StrategyConfig(),snap)
    setattr(quotes[0],field,D(value))
    with pytest.raises(ValueError,match='finite and positive'): validate_quotes(quotes,snap,RiskStatus())
