from decimal import Decimal

from .common import ONE, ZERO, VersionedAgent, clamp
from .ml_features import FEATURE_SCHEMA_VERSION, build_feature_vector
from .model_artifact import LogisticModelArtifact
from .models import (AgentHealth, PredictiveAdverseSelectionAgentOutput,
    PredictiveAdverseSelectionMetrics, PredictiveAdverseSelectionState, PredictiveAgentMode,
    semantic_fingerprint)


class PredictiveAdverseSelectionAgent(VersionedAgent):
    """SHADOW only. Inference accepts only fixed, validated logistic artifacts."""

    def __init__(self, config):
        super().__init__(config)
        self._artifact = None
        self._artifact_error = False

    def install_artifact(self, artifact: LogisticModelArtifact):
        try:
            self._artifact = LogisticModelArtifact.model_validate(artifact.model_dump())
            self._artifact_error = False
        except Exception:
            self._artifact = None
            self._artifact_error = True
            raise

    def artifact_unavailable(self):
        self._artifact = None
        self._artifact_error = True

    def _versioned(self, output):
        # Observational version includes model identity and predictions; supervisor
        # material version/fingerprint deliberately excludes this agent entirely.
        signature = semantic_fingerprint(output.model_dump(exclude={"version", "updated_at", "evidence_version"}))
        if signature != self._signature:
            self.version += 1
            self._signature = signature
        return output.model_copy(update={"version": self.version})

    def evaluate(self, evidence):
        disabled = not self.config.agents_enabled or not self.config.predictive_agent_enabled or self.config.predictive_agent_mode == PredictiveAgentMode.DISABLED
        base = dict(agent="PREDICTIVE_ADVERSE_SELECTION", mode=PredictiveAgentMode.DISABLED if disabled else PredictiveAgentMode.SHADOW,
            confidence=ZERO, spread_multiplier=ONE, bid_size_multiplier=ONE, ask_size_multiplier=ONE,
            simulated=evidence.simulated, evidence_version=evidence.version, version=self.version,
            updated_at=evidence.updated_at, feature_schema_version=FEATURE_SCHEMA_VERSION)
        if disabled:
            return self._versioned(PredictiveAdverseSelectionAgentOutput(**base, health=AgentHealth.DISABLED,
                state=PredictiveAdverseSelectionState.DISABLED, reasons=["predictive agent disabled"]))
        if self._artifact is None:
            return self._versioned(PredictiveAdverseSelectionAgentOutput(**base,
                health=AgentHealth.ERROR if self._artifact_error else AgentHealth.INSUFFICIENT_DATA,
                state=PredictiveAdverseSelectionState.ERROR if self._artifact_error else PredictiveAdverseSelectionState.UNAVAILABLE,
                reasons=["SHADOW ONLY: invalid artifact" if self._artifact_error else "SHADOW ONLY: no validated artifact supplied"]))
        artifact = self._artifact
        try:
            if evidence.market != artifact.provenance.market:
                raise ValueError("model market mismatch")
            if artifact.provenance.simulated and not evidence.simulated:
                raise ValueError("simulated model cannot imply live validated inference")
            bid = artifact.predict(build_feature_vector(evidence, "BID"))
            ask = artifact.predict(build_feature_vector(evidence, "ASK"))
            # Evidence support ratio is a heuristic, not probability/calibration certainty.
            confidence = clamp(Decimal(evidence.history_sample_count)/self.config.regime_min_samples)
            metrics = PredictiveAdverseSelectionMetrics(bid_adverse_probability=bid, ask_adverse_probability=ask,
                inference_confidence=confidence, markout_horizon_seconds=artifact.provenance.markout_horizon_seconds,
                last_inference_time=evidence.updated_at)
            if confidence < self.config.predictive_min_confidence:
                return self._versioned(PredictiveAdverseSelectionAgentOutput(**base, health=AgentHealth.INSUFFICIENT_DATA,
                    state=PredictiveAdverseSelectionState.UNAVAILABLE, model_provenance=artifact.provenance,
                    reasons=["SHADOW ONLY: inference evidence support below configured minimum"]))
            return self._versioned(PredictiveAdverseSelectionAgentOutput(**{**base, "confidence":confidence},
                health=AgentHealth.READY, state=PredictiveAdverseSelectionState.PREDICTED,
                metrics=metrics, model_provenance=artifact.provenance,
                reasons=["ML SHADOW: conditional adverse-fill probabilities; NO QUOTE AUTHORITY",
                         "evidence support is heuristic confidence; independent calibration remains research evidence"]))
        except Exception:
            # No exception text/path or stale probability can cross the public boundary.
            return self._versioned(PredictiveAdverseSelectionAgentOutput(**base, health=AgentHealth.ERROR,
                state=PredictiveAdverseSelectionState.ERROR, model_provenance=artifact.provenance,
                reasons=["SHADOW inference unavailable: feature/model contract failure"]))
