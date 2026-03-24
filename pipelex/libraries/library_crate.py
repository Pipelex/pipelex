import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from pipelex.core.bundles.pipelex_bundle_blueprint import PipeBlueprintUnion
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.domains.domain_blueprint import DomainBlueprint


class LibraryCrate(BaseModel):
    """Complete library content as qualified blueprints, ready to load into a live Library.

    The crate is a flat, domain-agnostic snapshot of all concepts, pipes, and domain metadata.
    Domain is encoded in the dictionary keys (e.g. 'scoring.WeightedScore',
    'scoring.compute_score'), not in a structural container.

    Includes source information so that validation errors can trace back to origin files.
    """

    model_config = ConfigDict(extra="forbid")

    concepts: dict[str, ConceptBlueprint | str] = Field(default_factory=dict)
    """concept_ref (domain.ConceptCode) -> ConceptBlueprint or string description"""

    pipes: dict[str, PipeBlueprintUnion] = Field(default_factory=dict)
    """pipe_ref (domain.pipe_code) -> PipeBlueprintUnion"""

    domains: dict[str, DomainBlueprint] = Field(default_factory=dict)
    """domain_code -> DomainBlueprint (first-write-wins across bundles)"""

    source_map: dict[str, str] = Field(default_factory=dict)
    """concept_ref or pipe_ref -> source file path (for error reporting)"""

    fingerprint: str = ""
    """SHA-256 hex digest of the serialized concepts + pipes content."""

    def compute_fingerprint(self) -> str:
        """Compute SHA-256 fingerprint from concepts and pipes content.

        Uses deterministic JSON serialization of concepts and pipes only
        (excludes domains, source_map, and fingerprint itself).
        """
        concepts_json: dict[str, object] = {}
        for ref, value in sorted(self.concepts.items()):
            concepts_json[ref] = value if isinstance(value, str) else value.model_dump(mode="json")
        pipes_json = {ref: blueprint.model_dump(mode="json") for ref, blueprint in sorted(self.pipes.items())}
        payload = {"concepts": concepts_json, "pipes": pipes_json}
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(serialized.encode()).hexdigest()
