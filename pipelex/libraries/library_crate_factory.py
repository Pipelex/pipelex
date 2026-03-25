from typing import TYPE_CHECKING

from pipelex import log
from pipelex.core.bundles.pipelex_bundle_blueprint import PipeBlueprintUnion, PipelexBundleBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.libraries.pipe.exceptions import PipeLibraryError

if TYPE_CHECKING:
    from pipelex.core.concepts.concept_blueprint import ConceptBlueprint


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
                        existing_source = source_map.get(concept_ref)
                        if existing_source is not None and existing_source == source:
                            msg = (
                                f"Concept '{concept_ref}' is declared twice in the same bundle file: '{existing_source}'. "
                                "Please remove the duplicate declaration."
                            )
                        else:
                            msg = (
                                f"Concept '{concept_ref}' is declared in two different bundle files: "
                                f"'{existing_source or 'unknown'}' and '{source or 'unknown'}'. "
                                "Please remove one of the declarations or rename one of the concepts."
                            )
                        raise ConceptLibraryError(msg)
                    concepts[concept_ref] = value
                    if source:
                        source_map[concept_ref] = source

            # Pipes
            if blueprint.pipe is not None:
                for pipe_code, pipe_blueprint in blueprint.pipe.items():
                    pipe_ref = PipeFactory.make_pipe_ref_with_domain(domain_code=domain_code, pipe_code=pipe_code)
                    if pipe_ref in pipes:
                        existing_source = source_map.get(pipe_ref)
                        if existing_source is not None and existing_source == source:
                            msg = (
                                f"Pipe '{pipe_ref}' is declared twice in the same bundle file: '{existing_source}'. "
                                "Please remove the duplicate declaration."
                            )
                        else:
                            msg = (
                                f"Pipe '{pipe_ref}' is declared in two different bundle files: "
                                f"'{existing_source or 'unknown'}' and '{source or 'unknown'}'. "
                                "Please remove one of the declarations or rename one of the pipes."
                            )
                        raise PipeLibraryError(msg)
                    pipes[pipe_ref] = pipe_blueprint
                    if source:
                        source_map[pipe_ref] = source

        fingerprint = LibraryCrate.compute_fingerprint_from_content(concepts=concepts, pipes=pipes)
        return LibraryCrate(
            concepts=concepts,
            pipes=pipes,
            domains=domains,
            source_map=source_map,
            fingerprint=fingerprint,
        )
