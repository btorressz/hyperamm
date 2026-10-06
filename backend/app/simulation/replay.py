from __future__ import annotations

from .models import SimulationDataset,SimulationFrame


def build_dataset(*,market:str,frames:list[SimulationFrame],source:str="caller-provided")->SimulationDataset:
    return SimulationDataset(market=market,frames=list(frames),source=source,simulated=True)


def bounded_frames(dataset:SimulationDataset,max_frames:int)->list[SimulationFrame]:
    if max_frames<2:raise ValueError("max_frames must be >= 2")
    if len(dataset.frames)>max_frames:
        raise ValueError(f"dataset has {len(dataset.frames)} frames; allowed maximum is {max_frames}")
    return list(dataset.frames)
