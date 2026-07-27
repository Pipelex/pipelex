import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipeBlueprintUnion


class LibraryCrate(BaseModel):
    """Complete library content as qualified blueprints, ready to load into a live Library.

    The crate is a flat, domain-agnostic snapshot of all concepts, pipes, and domain metadata.
    Domain is encoded in the dictionary keys (e.g. 'scoring.WeightedScore',
    'scoring.compute_score'), not in a structural container.

    Includes source information so that validation errors can trace back to origin files.
    """

    model_config = ConfigDict(extra="forbid")

    mthds_version: str = ""
    """MTHDS standard version the crate was normalized against (empty for a non-normalized transport crate)."""

    concepts: dict[str, ConceptBlueprint | str] = Field(default_factory=dict)
    """concept_ref (domain.ConceptCode) -> ConceptBlueprint or string description"""

    pipes: dict[str, PipeBlueprintUnion] = Field(default_factory=dict)
    """pipe_ref (domain.pipe_code) -> PipeBlueprintUnion"""

    domains: dict[str, DomainBlueprint] = Field(default_factory=dict)
    """domain_code -> DomainBlueprint (first-write-wins across bundles)"""

    source_map: dict[str, str] = Field(default_factory=dict)
    """concept_ref or pipe_ref -> source file path (for error reporting)"""

    python_sources: dict[str, str] = Field(default_factory=dict)
    """relpath (within the library dir) -> Python source text, captured WITHOUT importing.

    Carries the customer's PipeFunc and structure-class .py source alongside the method so it can
    travel to a sandbox and be registered + executed there. Populated only in sandbox-hosted load
    mode; empty for local/direct loads. Deliberately EXCLUDED from the fingerprint (see
    compute_fingerprint_from_content): the fingerprint represents library structure for dedupe, and
    folding source into it would break the structural-idempotency contract in load_from_crate.
    """

    fingerprint: str = ""
    """SHA-256 hex digest of the serialized concepts + pipes content (source is intentionally excluded)."""

    @staticmethod
    def compute_fingerprint_from_content(
        *,
        concepts: dict[str, "ConceptBlueprint | str"],
        pipes: dict[str, PipeBlueprintUnion],
    ) -> str:
        """Compute SHA-256 fingerprint from concepts and pipes content.

        Uses deterministic JSON serialization of concepts and pipes only
        (excludes domains, source_map, and fingerprint itself).
        """
        concepts_json: dict[str, object] = {}
        for ref, value in sorted(concepts.items()):
            concepts_json[ref] = value if isinstance(value, str) else value.model_dump(mode="json")
        pipes_json = {ref: blueprint.model_dump(mode="json") for ref, blueprint in sorted(pipes.items())}
        payload = {"concepts": concepts_json, "pipes": pipes_json}
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def compute_fingerprint(self) -> str:
        """Compute SHA-256 fingerprint from this crate's concepts and pipes."""
        return self.compute_fingerprint_from_content(concepts=self.concepts, pipes=self.pipes)

    @staticmethod
    def compute_normalized_fingerprint(
        *,
        concepts: dict[str, "ConceptBlueprint | str"],
        pipes: dict[str, PipeBlueprintUnion],
        domains: dict[str, DomainBlueprint],
    ) -> str:
        """Compute the semantic fingerprint of a normalized crate (D2 scope: concepts + pipes + domains).

        The hashed payload is `{concepts, pipes, domains}` with each object's provenance `source`
        removed (a change of file location must not change the digest); `source_map`, `mthds_version`,
        and the `fingerprint` member itself are excluded. Serialization is canonical — keys sorted at
        every level, no inter-token whitespace, non-ASCII as literal UTF-8 — so two producers agree
        byte-for-byte. This matches RFC 8785 (JSON Canonicalization Scheme) for the object / array /
        string / bool / integer payload a crate contains; full JCS number canonicalization is the
        forward contract for the rare float default value.
        """
        concepts_json: dict[str, object] = {}
        for ref, value in sorted(concepts.items()):
            concepts_json[ref] = value if isinstance(value, str) else _strip_source(value.model_dump(mode="json"))
        pipes_json = {ref: _strip_source(blueprint.model_dump(mode="json")) for ref, blueprint in sorted(pipes.items())}
        domains_json = {code: _strip_source(domain.model_dump(mode="json")) for code, domain in sorted(domains.items())}
        payload = {"concepts": concepts_json, "pipes": pipes_json, "domains": domains_json}
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def compute_normalized(self) -> str:
        """Compute the normalized (D2-scope) fingerprint from this crate's concepts, pipes, and domains."""
        return self.compute_normalized_fingerprint(concepts=self.concepts, pipes=self.pipes, domains=self.domains)


def _strip_source(dumped: dict[str, object]) -> dict[str, object]:
    """Drop the provenance `source` member from a dumped blueprint before hashing (it is not semantic)."""
    return {key: value for key, value in dumped.items() if key != "source"}
