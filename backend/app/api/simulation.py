from __future__ import annotations

from typing import Any

from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,model_validator

from app.dependencies import runtime
from app.simulation import OptimizationObjectiveConfig,SimulationConfig,SimulationService
from app.simulation.optimizer import HARD_MAX_CANDIDATES
from app.simulation.scenarios import ScenarioName


router=APIRouter(tags=["simulation"])


class SimulationRunRequest(BaseModel):
    scenario:ScenarioName=ScenarioName.QUIET
    frames:int=Field(default=120,ge=2,le=5000)
    simulation:SimulationConfig=Field(default_factory=SimulationConfig)


class OptimizationRequest(BaseModel):
    strategy_grid:dict[str,list[Any]]
    agent_grid:dict[str,list[Any]]
    training_scenarios:list[ScenarioName]=Field(min_length=1,max_length=8)
    validation_scenarios:list[ScenarioName]=Field(min_length=1,max_length=8)
    frames:int=Field(default=120,ge=2,le=1000)
    max_candidates:int=Field(default=32,ge=1,le=HARD_MAX_CANDIDATES)
    top_n:int=Field(default=5,ge=1,le=10)
    simulation:SimulationConfig=Field(default_factory=SimulationConfig)
    objective:OptimizationObjectiveConfig=Field(default_factory=OptimizationObjectiveConfig)

    @model_validator(mode="after")
    def grid_present(self):
        if not self.strategy_grid and not self.agent_grid:
            raise ValueError("optimization requires at least one strategy or agent parameter grid")
        return self


@router.get("/simulation/scenarios")
async def scenarios():
    return {"simulated":True,"scenarios":SimulationService().scenarios()}


@router.post("/simulation/run")
async def run_simulation(request:SimulationRunRequest,rt=Depends(runtime)):
    try:
        result=await SimulationService().run_scenario(
            scenario=request.scenario.value,frames=request.frames,strategy=rt.config.model_copy(deep=True),
            agents=rt.agent_config.model_copy(deep=True),risk=rt.risk_config.model_copy(deep=True),
            simulation=request.simulation.model_copy(deep=True),
        )
        return result.model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc


@router.post("/simulation/optimize")
async def optimize(request:OptimizationRequest,rt=Depends(runtime)):
    try:
        result=await SimulationService().optimize(
            strategy=rt.config.model_copy(deep=True),agents=rt.agent_config.model_copy(deep=True),
            risk=rt.risk_config.model_copy(deep=True),simulation=request.simulation.model_copy(deep=True),
            strategy_grid=request.strategy_grid,agent_grid=request.agent_grid,
            training_scenarios=[x.value for x in request.training_scenarios],
            validation_scenarios=[x.value for x in request.validation_scenarios],
            objective=request.objective,max_candidates=request.max_candidates,frames=request.frames,top_n=request.top_n,
        )
        return result.model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc
