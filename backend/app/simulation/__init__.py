"""Public research exports, loaded on demand to keep observation imports acyclic."""
from importlib import import_module

_EXPORTS = {
    'OptimizationObjectiveConfig': 'config', 'SimulationConfig': 'config',
    'SimulationDataset': 'models', 'SimulationEngine': 'engine',
    'SimulationFrame': 'models', 'SimulationMetrics': 'models',
    'SimulationResult': 'models', 'SimulationService': 'service',
    'StrategyOptimizer': 'optimizer', 'ScenarioName': 'scenarios',
    'generate_scenario': 'scenarios', 'scenario_catalog': 'scenarios',
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    value = getattr(import_module(f'.{module}', __name__), name)
    globals()[name] = value
    return value
