import hashlib
import json

from mthds.method_tree.models import MethodTree
from pydantic import BaseModel, ConfigDict, Field

from pipelex.core.bundle_resources.bundle_resource import BundleResources
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.method_trees.tree_bundle import TreeBundle, TreeBundleRef
from pipelex.libraries.exceptions import CrateIntegrityError
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

    python_sources: dict[str, str] = Field(default_factory=dict)
    """relpath (within the library dir) -> Python source text, captured WITHOUT importing.

    Carries the customer's PipeFunc and structure-class .py source alongside the method so it can
    travel to a sandbox and be registered + executed there. Populated only in sandbox-hosted load
    mode; empty for local/direct loads. Deliberately EXCLUDED from the fingerprint (see
    compute_fingerprint_from_content): the fingerprint represents library structure for dedupe, and
    folding source into it would break the structural-idempotency contract in load_from_crate.
    """

    bundle_resources: BundleResources = Field(default_factory=dict)
    """canonical bundle-relative path -> a file submitted with a bundle loaded from content strings.

    Carries the files a content-string bundle's steps read, such as a PipeDocGen `template_file`, wherever the
    crate is loaded again, a Temporal workflow included: a file read when the method loads travels inline, and one
    read only when its step runs may travel by reference to the run's storage (see `relocate_run_resources`).
    Empty for a library loaded from directories, whose steps read beside their files on disk. Like
    `python_sources`, it is transport-only: EXCLUDED from the fingerprint and from the normalized crate.
    """

    method_trees: dict[str, str] = Field(default_factory=dict)
    """tree key (`tree_key_of`) -> a method tree the host that assembled the crate listed its bundles' files in, as
    the JSON of its listing, a `MethodTree`, so the crate stays plain text wherever it travels, a Temporal payload
    included.

    A pipe reads a file its bundle names, such as a PipeDocGen `template_file`, only by resolving it in its bundle's
    tree (`tree_bundles`), never through `source_map`: a source is a label, which a caller sends with content strings
    and a bundle's own text can write, so a pipe loaded from content strings has no tree and reads only the files
    submitted with it (`bundle_resources`). Transport-only, like `python_sources`: EXCLUDED from the fingerprint and
    from the normalized crate, so a host path never reaches a caller through `/resolve`.
    """

    tree_bundles: dict[str, TreeBundleRef] = Field(default_factory=dict)
    """pipe_ref -> the member of `method_trees` the pipe's bundle was read as, for a pipe whose bundle the host that
    assembled the crate read from its disk. Transport-only, like `method_trees`."""

    def tree_bundles_by_pipe_ref(self) -> dict[str, TreeBundle]:
        """Each pipe whose bundle was read from a host's disk, with the member of its method tree the bundle was read as.

        Each tree is read back once, however many pipes its bundles define. A pipe of a bundle parsed from a string has
        no entry.

        Raises:
            CrateIntegrityError: A pipe names a tree the crate does not carry.
        """
        trees: dict[str, MethodTree] = {}
        tree_bundles: dict[str, TreeBundle] = {}
        for pipe_ref, tree_bundle_ref in self.tree_bundles.items():
            tree = trees.get(tree_bundle_ref.tree_key)
            if tree is None:
                tree_json = self.method_trees.get(tree_bundle_ref.tree_key)
                if tree_json is None:
                    msg = f"The crate names the method tree '{tree_bundle_ref.tree_key}' for pipe '{pipe_ref}' but carries no such tree."
                    raise CrateIntegrityError(msg)
                tree = MethodTree.model_validate_json(tree_json)
                trees[tree_bundle_ref.tree_key] = tree
            tree_bundles[pipe_ref] = TreeBundle(tree=tree, tree_path=tree_bundle_ref.tree_path)
        return tree_bundles

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
