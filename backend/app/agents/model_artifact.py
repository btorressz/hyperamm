"""Bounded JSON logistic coefficients; no executable serialization or ML imports."""
from math import exp
from decimal import Decimal
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from .models import AgentModel, ModelProvenance, semantic_fingerprint
from .ml_features import FEATURE_NAMES, FEATURE_SCHEMA_VERSION, FeatureSchema, FeatureVector

MAX_ARTIFACT_BYTES = 65536


class LogisticModelArtifact(AgentModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    artifact_format: Literal["hyperamm-logistic-json-v1"] = "hyperamm-logistic-json-v1"
    feature_schema: FeatureSchema = Field(default_factory=FeatureSchema)
    coefficients: tuple[Decimal, ...] = Field(min_length=len(FEATURE_NAMES), max_length=len(FEATURE_NAMES))
    intercept: Decimal = Field(ge=-100, le=100)
    provenance: ModelProvenance

    @model_validator(mode="after")
    def validate_artifact(self):
        if any(not c.is_finite() or not -100 <= c <= 100 for c in self.coefficients):
            raise ValueError("model coefficients outside bounded contract")
        if self.provenance.feature_schema_version != FEATURE_SCHEMA_VERSION:
            raise ValueError("model/schema mismatch")
        payload = self.model_dump()
        payload["provenance"].pop("model_sha256")
        if semantic_fingerprint(payload) != self.provenance.model_sha256:
            raise ValueError("artifact hash mismatch")
        return self

    @classmethod
    def seal(cls, *, coefficients, intercept, provenance):
        payload = dict(artifact_format="hyperamm-logistic-json-v1", feature_schema=FeatureSchema().model_dump(),
            coefficients=tuple(Decimal(str(c)) for c in coefficients), intercept=Decimal(str(intercept)),
            provenance={**provenance, "model_sha256": "0"*64})
        # Validate/canonicalize provenance defaults before computing its content identity.
        parsed = ModelProvenance(**payload["provenance"])
        payload["provenance"] = parsed.model_dump()
        payload["provenance"].pop("model_sha256")
        digest = semantic_fingerprint(payload)
        payload["provenance"]["model_sha256"] = digest
        return cls.model_validate(payload)

    def predict(self, vector: FeatureVector) -> Decimal:
        vector = FeatureVector.model_validate(vector.model_dump())
        # Fixed dimensionality and clipped features bound work to twelve multiplies.
        logit = self.intercept + sum((c*v for c,v in zip(self.coefficients, vector.values)), Decimal(0))
        bounded = max(Decimal(-60), min(Decimal(60), logit))
        return Decimal(str(1.0/(1.0+exp(-float(bounded)))))


def load_model_artifact(path) -> LogisticModelArtifact:
    """Only called at explicit trusted local operator setup, never quote evaluation."""
    with open(path, "rb") as stream:
        raw = stream.read(MAX_ARTIFACT_BYTES+1)
    if len(raw) > MAX_ARTIFACT_BYTES:
        raise ValueError("model artifact exceeds bounded size")
    return LogisticModelArtifact.model_validate_json(raw)
