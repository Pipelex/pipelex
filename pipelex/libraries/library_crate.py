import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.method_trees.tree_bundle import TreeBundleRef
from pipelex.mthds_parsing.pipelex_bundle_blueprint import ElaborationMetadata, PipeBlueprintUnion


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

    elaboration_metadata: dict[str, ElaborationMetadata] = Field(default_factory=dict)
    """pipe_ref -> how the bundle elaborator generated that synthetic pipe (the helpers of a
    ``preliminary_text`` PipeLLM), so a refusal raised while building a helper is reported on the pipe
    and the field the author wrote. Like ``source_map``, it is excluded from the fingerprint."""

    tree_bundles: dict[str, TreeBundleRef] = Field(default_factory=dict)
    """pipe_ref -> the method tree the pipe's bundle belongs to, named by its digest, and the bundle's tree path there.

    A pipe reads a file its bundle names, such as a PipeDocGen `template_file`, only by resolving it in its bundle's
    tree, never through `source_map`: a source is a label, which a caller sends with content strings and a bundle's own
    text can write. The crate carries no tree's files nor listing, and no path of the host that assembled it: a pipe
    built from the crate resolves a reference lexically and reads nothing, and the process that uses a file, a
    `PipeFunc` call or a `PipeDocGen` print, reads it through the method file store by the tree's digest. Bundles parsed
    from content strings name the tree of the files submitted with them, with no tree path, and none when no file was
    submitted. Transport-only: EXCLUDED from the fingerprint and from the normalized crate.
    """

    def tree_digests(self) -> list[str]:
        """The digest of every tree the crate's pipes belong to, each once, sorted."""
        return sorted({tree_bundle_ref.tree_digest for tree_bundle_ref in self.tree_bundles.values()})

    def concepts_only(self) -> "LibraryCrate":
        """The crate's concepts and domains, with none of its pipes: what a process typing the run's data loads.

        Its fingerprint is its own, computed from its concepts, so two runs whose methods declare the same concepts share
        it whatever their pipes.
        """
        return LibraryCrate(
            mthds_version=self.mthds_version,
            concepts=dict(self.concepts),
            domains=dict(self.domains),
            fingerprint=self.compute_fingerprint_from_content(concepts=self.concepts, pipes={}),
        )

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
