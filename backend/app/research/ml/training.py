"""Optional offline sklearn fit; exports inert JSON coefficients for shadow inference."""
from datetime import datetime, timezone
from decimal import Decimal

from pydantic import Field

from app.agents.model_artifact import LogisticModelArtifact
from app.agents.models import AgentModel, semantic_fingerprint
from .dataset import OfflineDataset, validate_independent_windows
from .validation import PredictionOutcome, evaluate_predictions


class TrainingConfig(AgentModel):
    regularization_c: Decimal = Field(default=Decimal(1), gt=0, le=100)
    max_iterations: int = Field(default=200, ge=10, le=1000)
    minimum_training_samples: int = Field(default=20, ge=2, le=100000)
    minimum_validation_samples: int = Field(default=10, ge=1, le=100000)
    random_state: int = Field(default=0, ge=0, le=2147483647)


def train_logistic_model(*, training: OfflineDataset, validation: OfflineDataset,
                         config: TrainingConfig | None = None, model_name="passive-adverse", model_version="1",
                         trained_at=None):
    config = config or TrainingConfig()
    config = TrainingConfig.model_validate(config.model_dump())
    validate_independent_windows(training, validation)
    if training.sample_count < config.minimum_training_samples or validation.sample_count < config.minimum_validation_samples:
        raise ValueError("insufficient training/validation sample support")
    if len({s.adverse for s in training.samples}) != 2:
        raise ValueError("classification training requires both classes")
    try:
        import sklearn
        from sklearn.linear_model import LogisticRegression
    except ImportError as exc:
        raise RuntimeError("offline training requires the optional ml dependency") from exc
    # sklearn's arrays/floats/NumPy remain in this offline research boundary.
    estimator = LogisticRegression(C=float(config.regularization_c),max_iter=config.max_iterations,
        random_state=config.random_state,solver="lbfgs")
    estimator.fit([[float(v) for v in s.features.values] for s in training.samples], [int(s.adverse) for s in training.samples])
    if int(estimator.n_iter_[0]) >= config.max_iterations:
        raise ValueError("model did not converge within bounded training iterations")
    probabilities = estimator.predict_proba([[float(v) for v in s.features.values] for s in validation.samples])[:,1]
    report = evaluate_predictions([PredictionOutcome(side=s.features.side,probability=Decimal(str(float(p))),
        markout_bps=s.signed_markout_bps) for s,p in zip(validation.samples,probabilities)],
        partition="validation",horizon_seconds=validation.markout_horizon_seconds,simulated=validation.simulated)
    artifact = LogisticModelArtifact.seal(coefficients=estimator.coef_[0],intercept=estimator.intercept_[0],provenance=dict(
        model_name=model_name,model_version=model_version,model_type="LOGISTIC_REGRESSION",
        feature_schema_version=training.feature_schema_version,
        training_dataset_fingerprint=training.fingerprint,validation_dataset_fingerprint=validation.fingerprint,
        training_config_fingerprint=semantic_fingerprint(config),trained_at=trained_at or datetime.now(timezone.utc),
        training_window_start=training.time_start,training_window_end=training.time_end,
        validation_window_start=validation.time_start,validation_window_end=validation.time_end,
        training_sample_count=training.sample_count,validation_sample_count=validation.sample_count,
        validation_metrics=report.metrics,library_version=sklearn.__version__,market=training.market,
        simulated=training.simulated,markout_horizon_seconds=training.markout_horizon_seconds))
    return artifact, report


def main():
    """Explicit local CLI. No retraining loop, runtime hook or automatic promotion."""
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser(description="Offline logistic training; SHADOW artifact only")
    parser.add_argument('--training',type=Path,required=True)
    parser.add_argument('--validation',type=Path,required=True)
    parser.add_argument('--artifact',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    training=OfflineDataset.model_validate_json(args.training.read_bytes())
    validation=OfflineDataset.model_validate_json(args.validation.read_bytes())
    artifact,report=train_logistic_model(training=training,validation=validation)
    args.artifact.write_text(artifact.model_dump_json(indent=2)+'\n')
    args.report.write_text(report.model_dump_json(indent=2)+'\n')


if __name__=='__main__':
    main()
