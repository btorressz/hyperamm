from __future__ import annotations

from typing import Any
from copy import deepcopy
import logging

from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,ConfigDict,Field,model_validator

from app.dependencies import runtime
from app.simulation import OptimizationObjectiveConfig,SimulationConfig,SimulationService
from app.simulation.optimizer import HARD_MAX_CANDIDATES
from app.simulation.scenarios import ScenarioName
from app.simulation.executor import ResearchBusyError
from app.infrastructure.research import ResearchUnavailableError
from app.simulation.research_vault import ResearchProposal
from app.simulation.market_profiles import ResearchPerpMarketId
from app.api.research_markets import selected_profile


router=APIRouter(tags=["simulation"])
logger=logging.getLogger(__name__)


class SimulationRunRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    scenario:ScenarioName=ScenarioName.QUIET
    frames:int=Field(default=120,ge=2,le=5000)
    simulation:SimulationConfig=Field(default_factory=SimulationConfig)
    research:ResearchProposal|None=None
    research_market:ResearchPerpMarketId|None=None

    @model_validator(mode="after")
    def frame_bound(self):
        validate_research_controls(self)
        if self.frames>self.simulation.max_frames:
            raise ValueError(f"frames {self.frames} exceeds simulation max_frames {self.simulation.max_frames}")
        return self


class OptimizationRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    strategy_grid:dict[str,list[Any]]
    agent_grid:dict[str,list[Any]]
    training_scenarios:list[ScenarioName]=Field(min_length=1,max_length=8)
    validation_scenarios:list[ScenarioName]=Field(min_length=1,max_length=8)
    frames:int=Field(default=120,ge=2,le=1000)
    max_candidates:int=Field(default=32,ge=1,le=HARD_MAX_CANDIDATES)
    top_n:int=Field(default=5,ge=1,le=10)
    simulation:SimulationConfig=Field(default_factory=SimulationConfig)
    research:ResearchProposal|None=None
    research_market:ResearchPerpMarketId|None=None
    objective:OptimizationObjectiveConfig=Field(default_factory=OptimizationObjectiveConfig)

    @model_validator(mode="after")
    def grid_present(self):
        validate_research_controls(self)
        if not self.strategy_grid and not self.agent_grid:
            raise ValueError("optimization requires at least one strategy or agent parameter grid")
        if self.frames>self.simulation.max_frames:
            raise ValueError(f"frames {self.frames} exceeds simulation max_frames {self.simulation.max_frames}")
        return self


def validate_research_controls(request):
    if request.research is not None and request.simulation.model_fields_set & {"initial_equity_quote", "accounting", "fill_model"}:
        raise ValueError("research owns capital and accounting; simulation may supply only frame/trace controls")


def isolated_simulation(request):
    return (request.research.config.to_simulation(request.simulation) if request.research
            else request.simulation.model_copy(deep=True))


@router.get("/simulation/scenarios")
async def scenarios():
    return {"simulated":True,"scenarios":SimulationService().scenarios()}


@router.post("/simulation/run")
async def run_simulation(request:SimulationRunRequest,http_request:Request,rt=Depends(runtime)):
    try:
        market_profile = await selected_profile(http_request, request.research_market)
        result=await http_request.app.state.simulation_executor.execute("run_scenario",
            scenario=request.scenario.value,frames=request.frames,strategy=rt.config.model_copy(deep=True),
            agents=rt.agent_config.model_copy(deep=True),risk=rt.risk_config.model_copy(deep=True),
            simulation=isolated_simulation(request),
            **({"market_profile": market_profile} if market_profile is not None else {}),
        )
        if request.research:
            result.research_configuration=request.research.provenance()
        return result.model_dump(mode="json")
    except ResearchUnavailableError as exc:
        raise HTTPException(status_code=503,detail=str(exc)) from exc
    except ResearchBusyError as exc:
        raise HTTPException(status_code=429,detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Phase 10 simulation failed")
        raise HTTPException(status_code=500,detail="Phase 10 simulation failed") from exc


@router.post("/simulation/optimize")
async def optimize(request:OptimizationRequest,http_request:Request,rt=Depends(runtime)):
    try:
        market_profile = await selected_profile(http_request, request.research_market)
        result=await http_request.app.state.simulation_executor.execute("optimize",
            strategy=rt.config.model_copy(deep=True),agents=rt.agent_config.model_copy(deep=True),
            risk=rt.risk_config.model_copy(deep=True),simulation=isolated_simulation(request),
            strategy_grid=deepcopy(request.strategy_grid),agent_grid=deepcopy(request.agent_grid),
            training_scenarios=[x.value for x in request.training_scenarios],
            validation_scenarios=[x.value for x in request.validation_scenarios],
            objective=request.objective.model_copy(deep=True),max_candidates=request.max_candidates,frames=request.frames,top_n=request.top_n,
            **({"market_profile": market_profile} if market_profile is not None else {}),
        )
        if request.research:
            result.research_configuration=request.research.provenance()
        return result.model_dump(mode="json")
    except ResearchUnavailableError as exc:
        raise HTTPException(status_code=503,detail=str(exc)) from exc
    except ResearchBusyError as exc:
        raise HTTPException(status_code=429,detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Phase 10 optimization failed")
        raise HTTPException(status_code=500,detail="Phase 10 optimization failed") from exc
