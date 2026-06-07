from typing import TYPE_CHECKING, NamedTuple

from pipelex import log
from pipelex.core.bundles.pipelex_bundle_blueprint import PipeBlueprintUnion, PipelexBundleBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.libraries.collision_messages import duplicate_ref_msg
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.libraries.pipe.exceptions import PipeLibraryError

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
    ) -> LibraryCrate:
        """Build a LibraryCrate from parsed bundle blueprints.

        For each bundle:
        1. Qualify concept codes with the bundle's domain -> concept_ref keys
        2. Qualify pipe codes with the bundle's domain -> pipe_ref keys
        3. Preserve string-described concepts as-is (no normalization to ConceptBlueprint)
        4. Collect domain metadata (first-write-wins per domain code)
        5. Track source file for each concept_ref and pipe_ref
        6. Detect duplicate refs across bundles (raise ConceptLibraryError / PipeLibraryError)
        7. Compute SHA-256 fingerprint

        Args:
            blueprints: List of parsed MTHDS bundle blueprints

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

            # Domain metadata: first-write-wins
            if domain_code not in domains:
                domains[domain_code] = DomainBlueprint(
                    source=source,
                    code=domain_code,
                    description=blueprint.description or "",
                    system_prompt=blueprint.system_prompt,
                    main_pipe=blueprint.main_pipe,
                )
            else:
                existing = domains[domain_code]
                new_description = blueprint.description or ""
                if existing.description != new_description:
                    log.warning(
                        f"Domain '{domain_code}' declared with different descriptions: "
                        f"'{existing.description}' vs '{new_description}'. Keeping the first.",
                    )
                if existing.system_prompt != blueprint.system_prompt:
                    log.warning(
                        f"Domain '{domain_code}' declared with different system_prompts. Keeping the first.",
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

        # Concept references resolve against the merged library, not per file. Running this after
        # the merge lets a concept declared in one bundle be referenced by bare code from a sibling
        # bundle of the same domain (the additive multi-file authoring model).
        cls._validate_concept_references(blueprints=blueprints, declared_concept_refs=set(concepts.keys()))

        fingerprint = LibraryCrate.compute_fingerprint_from_content(concepts=concepts, pipes=pipes)
        return LibraryCrate(
            concepts=concepts,
            pipes=pipes,
            domains=domains,
            source_map=source_map,
            fingerprint=fingerprint,
        )

    @classmethod
    def _validate_concept_references(
        cls,
        blueprints: list[PipelexBundleBlueprint],
        declared_concept_refs: set[str],
    ) -> None:
        """Validate that every same-domain concept reference resolves against the merged library.

        Runs after the per-bundle merge so a concept declared in one file can be referenced by
        bare code from a sibling file of the same domain. References are deferred where another
        layer owns them: cross-package refs ('alias->...') resolve at dependency-load time, and
        external-domain refs resolve when their domain's bundles load. Native concepts are always
        allowed. Every unresolved reference is accumulated and reported together so the author sees
        all of them at once.

        Args:
            blueprints: The parsed bundles whose concept references are being checked.
            declared_concept_refs: The fully qualified concept refs present in the merged crate.

        Raises:
            ConceptLibraryError: If any same-domain/bare reference is neither declared nor native.
        """
        native_codes = {native.value for native in NativeConceptCode.values_list()}
        undeclared: list[str] = []
        for blueprint in blueprints:
            domain_code = blueprint.domain
            source = blueprint.source
            for concept_ref_or_code, context in blueprint.collect_concept_references():
                # Cross-package references are resolved at dependency-load time.
                if QualifiedRef.has_cross_package_prefix(concept_ref_or_code):
                    continue
                ref = QualifiedRef.parse(concept_ref_or_code)
                # External-domain references resolve when their own domain's bundles load.
                if ref.is_external_to(domain_code):
                    continue
                # Native concepts are always available.
                if ref.local_code in native_codes:
                    continue
                concept_ref = ConceptFactory.make_concept_ref_with_domain(domain_code=domain_code, concept_code=ref.local_code)
                if concept_ref not in declared_concept_refs:
                    undeclared.append(
                        f"'{concept_ref_or_code}' in {context} is not declared in domain '{domain_code}' (source: '{source or 'unknown'}')"
                    )

        if undeclared:
            declared_list = sorted(declared_concept_refs) if declared_concept_refs else "(none)"
            msg = (
                "The following concept references could not be resolved against the merged library "
                "and are not native concepts:\n  - "
                + "\n  - ".join(undeclared)
                + f"\nDeclared concepts: {declared_list}."
                + f"\nNative concepts: {sorted(native_codes)}."
            )
            raise ConceptLibraryError(msg)

    @classmethod
    def _reconcile_pipe_collision(
        cls,
        pipe_ref: str,
        existing: PipeDeclaration,
        incoming: PipeDeclaration,
    ) -> PipeDeclaration:
        """Resolve two declarations of the same pipe_ref into a single winning declaration.

        A PipeSignature is a forward declaration ("header"); a concrete pipe is its
        definition. A concrete beats a signature, and the contracts must agree whenever a
        signature is involved. Two concrete pipes are a genuine duplicate (error). Two
        matching signatures collapse to one via a deterministic, load-order-independent
        tie-break. Returns the winning (blueprint, source) declaration.
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

        # At least one is a signature: the declarations' contracts must match.
        if not existing.blueprint.contract_equals(incoming.blueprint):
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
    def _contract_mismatch_msg(pipe_ref: str, existing: PipeDeclaration, incoming: PipeDeclaration) -> str:
        return (
            f"Pipe '{pipe_ref}' is declared with mismatched contracts: "
            f"'{existing.source or 'unknown'}' has inputs={existing.blueprint.inputs or {}}, output='{existing.blueprint.output}' "
            f"while '{incoming.source or 'unknown'}' has inputs={incoming.blueprint.inputs or {}}, output='{incoming.blueprint.output}'. "
            "A forward declaration (PipeSignature) and the matching declaration must agree on inputs and output."
        )
