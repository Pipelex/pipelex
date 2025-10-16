from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_library import ConceptLibrary
from pipelex.core.domains.domain import Domain
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.domains.domain_factory import DomainFactory
from pipelex.core.domains.domain_library import DomainLibrary
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.pipes.pipe_library import PipeLibrary
from pipelex.core.validation import report_validation_error
from pipelex.exceptions import (
    ConceptDefinitionError,
    DomainDefinitionError,
    LibraryLoadingError,
    PipeDefinitionError,
)


class Library(BaseModel):
    """A Library bundles together domain, concept, and pipe libraries for a specific context.

    This represents a complete set of Pipelex definitions (domains, concepts, pipes)
    that can be loaded and used together, typically for a single pipeline run.

    Each Library (except BASE) inherits native concepts and base pipes from the BASE library.
    """

    domain_library: DomainLibrary = Field(default_factory=DomainLibrary.make_empty)
    concept_library: ConceptLibrary = Field(default_factory=ConceptLibrary.make_empty)
    pipe_library: PipeLibrary = Field(default_factory=PipeLibrary.make_empty)

    @classmethod
    def make_empty(cls) -> "Library":
        """Create an empty library with initialized concept library (includes native concepts).

        This should only be used for the BASE library.
        """
        return cls.make_base()

    @classmethod
    def make_base(cls) -> "Library":
        """Create the BASE library that contains native concepts and builder pipes."""
        # 1 - Concept library, add the native concepts
        concept_library = ConceptLibrary.make_empty()

        # 2 - Pipe library, add the builder pipes
        pipe_library = PipeLibrary.make_empty()

        # 3 - Domain library, add the domains
        domain_library = DomainLibrary.make_empty()

        library = cls(
            domain_library=domain_library,
            concept_library=concept_library,
            pipe_library=pipe_library,
        )

        library.load_from_plx_files(
            plx_file_paths=[
                Path("pipelex/builder/builder.plx"),
                Path("pipelex/builder/pipe/pipe_design.plx"),
                Path("pipelex/builder/concept/concept.plx"),
            ]
        )

        return library

    def get_domain_library(self) -> DomainLibrary:
        return self.domain_library

    def get_concept_library(self) -> ConceptLibrary:
        return self.concept_library

    def get_pipe_library(self) -> PipeLibrary:
        return self.pipe_library

    def teardown(self) -> None:
        """Teardown all libraries in this bundle."""
        self.pipe_library.teardown()
        self.concept_library.teardown()
        self.domain_library.teardown()

    def validate_with_libraries(self) -> None:
        """Validate all libraries in this bundle."""
        self.concept_library.validate_with_libraries()
        self.pipe_library.validate_with_libraries()
        self.domain_library.validate_with_libraries()

    def load_from_blueprints(self, blueprints: list[PipelexBundleBlueprint]) -> list[PipeAbstract]:
        """Load domains, concepts, and pipes from a list of blueprints.

        Args:
            blueprints: List of parsed PLX blueprints to load

        Returns:
            List of all pipes that were loaded
        """
        all_pipes: list[PipeAbstract] = []

        # Load all domains first
        all_domains: list[Domain] = []
        for blueprint in blueprints:
            domain = self._load_domain_from_blueprint(blueprint)
            all_domains.append(domain)
        self.domain_library.add_domains(domains=all_domains)

        # Load all concepts second
        all_concepts: list[Concept] = []
        for blueprint in blueprints:
            concepts = self._load_concepts_from_blueprint(blueprint)
            all_concepts.extend(concepts)
        self.concept_library.add_concepts(concepts=all_concepts)

        # Load all pipes third
        for blueprint in blueprints:
            pipes = self._load_pipes_from_blueprint(blueprint)
            all_pipes.extend(pipes)
        self.pipe_library.add_pipes(pipes=all_pipes)

        return all_pipes

    def _load_domain_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> Domain:
        """Load a domain from a blueprint."""
        return DomainFactory.make_from_blueprint(
            blueprint=DomainBlueprint(
                source=blueprint.source,
                code=blueprint.domain,
                description=blueprint.description or "",
                system_prompt=blueprint.system_prompt,
            ),
        )

    def _load_concepts_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> list[Concept]:
        """Load concepts from a blueprint."""
        if blueprint.concept is None:
            return []

        concepts: list[Concept] = []
        for concept_code, concept_blueprint_or_description in blueprint.concept.items():
            concept = ConceptFactory.make_from_blueprint_or_description(
                domain=blueprint.domain,
                concept_code=concept_code,
                concept_codes_from_the_same_domain=list(blueprint.concept.keys()),
                concept_blueprint_or_description=concept_blueprint_or_description,
            )
            concepts.append(concept)
        return concepts

    def _load_pipes_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> list[PipeAbstract]:
        """Load pipes from a blueprint."""
        pipes: list[PipeAbstract] = []
        if blueprint.pipe is not None:
            for pipe_name, pipe_blueprint in blueprint.pipe.items():
                pipe = PipeFactory.make_from_blueprint(
                    domain=blueprint.domain,
                    pipe_code=pipe_name,
                    blueprint=pipe_blueprint,
                    concept_codes_from_the_same_domain=list(blueprint.concept.keys()) if blueprint.concept else None,
                )
                pipes.append(pipe)
        return pipes

    def remove_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> None:
        if blueprint.pipe is not None:
            self.pipe_library.remove_pipes_by_codes(pipe_codes=list(blueprint.pipe.keys()))

        # Remove concepts (they may depend on domain)
        if blueprint.concept is not None:
            concept_codes_to_remove = [
                ConceptFactory.make_concept_string_with_domain(domain=blueprint.domain, concept_code=concept_code)
                for concept_code in blueprint.concept
            ]
            self.concept_library.remove_concepts_by_codes(concept_codes=concept_codes_to_remove)

        self.domain_library.remove_domain_by_code(domain_code=blueprint.domain)

    def validate_library(self):
        self.validate_with_libraries()

    ############################################################
    # Library loading from sources
    ############################################################

    def load_from_plx_files(self, plx_file_paths: list[Path]) -> None:
        """Load library from a list of PLX file paths.

        This method:
        1. Parses blueprints from PLX files
        2. Loads blueprints into the library

        Note: Module imports and registry loading should be done by the LibraryManager
        before calling this method.

        Args:
            plx_file_paths: List of PLX file paths to load.
        """
        blueprints: list[PipelexBundleBlueprint] = []
        for plx_file_path in plx_file_paths:
            try:
                blueprint = PipelexInterpreter(file_path=plx_file_path).make_pipelex_bundle_blueprint()
            except FileNotFoundError as file_not_found_error:
                msg = f"Could not find PLX blueprint at '{plx_file_path}'"
                raise LibraryLoadingError(msg) from file_not_found_error
            except PipeDefinitionError as pipe_def_error:
                msg = f"Could not load PLX blueprint from '{plx_file_path}': {pipe_def_error}"
                raise LibraryLoadingError(msg) from pipe_def_error
            except ValidationError as validation_error:
                validation_error_msg = report_validation_error(category="plx", validation_error=validation_error)
                msg = f"Could not load PLX blueprint from '{plx_file_path}' because of: {validation_error_msg}"
                raise LibraryLoadingError(msg) from validation_error
            blueprint.source = str(plx_file_path)
            blueprints.append(blueprint)

        # Load all blueprints into the library
        try:
            self.load_from_blueprints(blueprints=blueprints)
        except DomainDefinitionError as domain_def_error:
            msg = f"Could not load domains from blueprints: {domain_def_error}"
            raise LibraryLoadingError(msg) from domain_def_error
        except ConceptDefinitionError as concept_def_error:
            msg = f"Could not load concepts from blueprints: {concept_def_error}"
            raise LibraryLoadingError(msg) from concept_def_error
        except PipeDefinitionError as pipe_def_error:
            msg = f"Could not load pipes from blueprints: {pipe_def_error}"
            raise LibraryLoadingError(msg) from pipe_def_error
        except ValidationError as validation_error:
            validation_error_msg = report_validation_error(category="plx", validation_error=validation_error)
            msg = f"Could not load blueprints because of: {validation_error_msg}"
            raise LibraryLoadingError(msg) from validation_error
