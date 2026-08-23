from typing import TYPE_CHECKING, NamedTuple

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.libraries.collision_messages import duplicate_ref_msg
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.libraries.contract_match import contracts_match
from pipelex.libraries.domain.domain_metadata_merge import merge_domain_metadata_field
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.libraries.pipe.exceptions import PipeLibraryError
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipeBlueprintUnion, PipelexBundleBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory

if TYPE_CHECKING:
    from pipelex.core.concepts.concept_blueprint import ConceptBlueprint


class PipeDeclaration(NamedTuple):
    """One declaration of a pipe: its blueprint paired with the bundle file it came from.

    Used by the library merge to reconcile two declarations of the same pipe_ref while keeping
    the winning blueprint and its source together (so source_map always follows the winner).
    """

    blueprint: PipeBlueprintUnion
    source: str | None


class LibraryCrateFactory:
    """Builds a LibraryCrate from parsed bundle blueprints."""

    @classmethod
    def make_from_blueprints(
        cls,
        blueprints: list[PipelexBundleBlueprint],
        *,
        python_sources: dict[str, str] | None = None,
    ) -> LibraryCrate:
        """Build a LibraryCrate from parsed bundle blueprints.

        For each bundle:
        1. Qualify concept codes with the bundle's domain -> concept_ref keys
        2. Qualify pipe codes with the bundle's domain -> pipe_ref keys
        3. Preserve string-described concepts as-is (no normalization to ConceptBlueprint)
        4. Collect domain metadata (order-independent, omission-quiet merge per domain code)
        5. Track source file for each concept_ref and pipe_ref
        6. Detect duplicate refs across bundles (raise ConceptLibraryError / PipeLibraryError)
        7. Compute SHA-256 fingerprint

        Args:
            blueprints: List of parsed MTHDS bundle blueprints
            python_sources: Optional relpath -> Python source text captured (without importing) in
                sandbox-hosted load mode. Attached verbatim to the crate; intentionally NOT folded
                into the fingerprint (the fingerprint represents library structure for dedupe).

        Returns:
            A LibraryCrate with all content merged and fingerprinted
        """
        concepts: dict[str, ConceptBlueprint | str] = {}
        pipes: dict[str, PipeBlueprintUnion] = {}
        domains: dict[str, DomainBlueprint] = {}
        source_map: dict[str, str] = {}

        for blueprint in blueprints:
            domain_code = blueprint.domain
            source = blueprint.source

            # Domain metadata: order-independent, omission-quiet merge (see merge_domain_metadata_field).
            if domain_code not in domains:
                domains[domain_code] = DomainBlueprint(
                    source=source,
                    code=domain_code,
                    description=blueprint.description or "",
                    system_prompt=blueprint.system_prompt,
                    main_pipe=blueprint.main_pipe,
                )
            else:
                # Fold this file's domain metadata into the established blueprint: an omitted field
                # defers to whichever same-domain file declared it, so the root's header wins over
                # membership-only siblings regardless of load order. `main_pipe` is crate metadata
                # too: codegen consumers use it to select the default pipe, even though the runtime
                # Domain currently drops it.
                existing = domains[domain_code]
                existing.description = (
                    merge_domain_metadata_field(
                        domain_code=domain_code,
                        field_label="description",
                        established=existing.description,
                        incoming=blueprint.description,
                        show_values_on_conflict=True,
                    )
                    or ""
                )
                existing.system_prompt = merge_domain_metadata_field(
                    domain_code=domain_code,
                    field_label="system_prompt",
                    established=existing.system_prompt,
                    incoming=blueprint.system_prompt,
                    show_values_on_conflict=False,
                )
                existing.main_pipe = merge_domain_metadata_field(
                    domain_code=domain_code,
                    field_label="main_pipe",
                    established=existing.main_pipe,
                    incoming=blueprint.main_pipe,
                    show_values_on_conflict=True,
                )

            # Concepts
            if blueprint.concept is not None:
                for concept_code, value in blueprint.concept.items():
                    concept_ref = ConceptFactory.make_concept_ref_with_domain(domain_code=domain_code, concept_code=concept_code)
                    if concept_ref in concepts:
                        raise ConceptLibraryError(
                            duplicate_ref_msg(
                                ref_kind="concept",
                                ref=concept_ref,
                                existing_source=source_map.get(concept_ref),
                                incoming_source=source,
                            )
                        )
                    concepts[concept_ref] = value
                    if source:
                        source_map[concept_ref] = source

            # Pipes
            if blueprint.pipe is not None:
                for pipe_code, pipe_blueprint in blueprint.pipe.items():
                    pipe_ref = PipeFactory.make_pipe_ref_with_domain(domain_code=domain_code, pipe_code=pipe_code)
                    if pipe_ref in pipes:
                        winner = cls._reconcile_pipe_collision(
                            pipe_ref=pipe_ref,
                            existing=PipeDeclaration(blueprint=pipes[pipe_ref], source=source_map.get(pipe_ref)),
                            incoming=PipeDeclaration(blueprint=pipe_blueprint, source=source),
                            domain_code=domain_code,
                        )
                        # source_map must always track the winner's file (or drop the entry when
                        # the winner has no source) so it never points at the discarded declaration.
                        pipes[pipe_ref] = winner.blueprint
                        if winner.source:
                            source_map[pipe_ref] = winner.source
                        else:
                            source_map.pop(pipe_ref, None)
                        continue
                    pipes[pipe_ref] = pipe_blueprint
                    if source:
                        source_map[pipe_ref] = source

        # Concept-reference validation is NOT done here: this factory performs a world-agnostic
        # structural merge. Same-domain concept references resolve against the live library (which
        # may hold concepts from prior load batches), so that check lives in the loader
        # (`LibraryManager.load_from_blueprints` -> `validate_concept_references_in_blueprints`).
        fingerprint = LibraryCrate.compute_fingerprint_from_content(concepts=concepts, pipes=pipes)
        return LibraryCrate(
            concepts=concepts,
            pipes=pipes,
            domains=domains,
            source_map=source_map,
            python_sources=python_sources or {},
            fingerprint=fingerprint,
        )

    @classmethod
    def _reconcile_pipe_collision(
        cls,
        pipe_ref: str,
        *,
        existing: PipeDeclaration,
        incoming: PipeDeclaration,
        domain_code: str,
    ) -> PipeDeclaration:
        """Resolve two declarations of the same pipe_ref into a single winning declaration.

        A PipeSignature is a forward declaration ("header"); a concrete pipe is its
        definition. A concrete beats a signature, and the contracts must agree whenever a
        signature is involved. Two concrete pipes are a genuine duplicate (error). Two
        matching signatures collapse to one via a deterministic, load-order-independent
        tie-break. Returns the winning (blueprint, source) declaration.

        Both declarations share ``domain_code`` (they collided on the same qualified ``pipe_ref``),
        which the contract check uses to normalize bare and same-domain-qualified concept spellings
        to one identity.
        """
        existing_is_signature = existing.blueprint.is_signature
        incoming_is_signature = incoming.blueprint.is_signature

        # Both concrete -> genuine duplicate (unchanged behavior).
        if not existing_is_signature and not incoming_is_signature:
            raise PipeLibraryError(
                duplicate_ref_msg(
                    ref_kind="pipe",
                    ref=pipe_ref,
                    existing_source=existing.source,
                    incoming_source=incoming.source,
                )
            )

        # At least one is a signature: the declarations' contracts must match (normalized identity).
        if not contracts_match(existing=existing.blueprint, incoming=incoming.blueprint, domain_code=domain_code):
            raise PipeLibraryError(cls._contract_mismatch_msg(pipe_ref=pipe_ref, existing=existing, incoming=incoming))

        # A concrete definition beats a forward declaration.
        if existing_is_signature and not incoming_is_signature:
            return incoming
        if incoming_is_signature and not existing_is_signature:
            return existing

        # Two signatures with matching contracts: pick a deterministic winner so the merged
        # crate (and therefore its fingerprint) does not depend on bundle load order.
        return min(existing, incoming, key=cls._declaration_sort_key)

    @staticmethod
    def _declaration_sort_key(declaration: PipeDeclaration) -> tuple[str, str]:
        """Order-independent key for tie-breaking two pipe signatures with matching contracts."""
        return (declaration.blueprint.model_dump_json(), declaration.source or "")

    @staticmethod
    def _contract_mismatch_msg(pipe_ref: str, *, existing: PipeDeclaration, incoming: PipeDeclaration) -> str:
        return (
            f"Pipe '{pipe_ref}' is declared with mismatched contracts: "
            f"'{existing.source or 'unknown'}' has inputs={existing.blueprint.inputs_concept_specs or {}}, output='{existing.blueprint.output}' "
            f"while '{incoming.source or 'unknown'}' has inputs={incoming.blueprint.inputs_concept_specs or {}}, "
            f"output='{incoming.blueprint.output}'. "
            "A forward declaration (PipeSignature) and the matching declaration must agree on inputs and output."
        )
