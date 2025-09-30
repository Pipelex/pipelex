import os
from pathlib import Path
from typing import ClassVar

from pydantic import ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.config import get_config
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
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
from pipelex.exceptions import (
    ConceptDefinitionError,
    ConceptLibraryError,
    ConceptLoadingError,
    DomainDefinitionError,
    DomainLoadingError,
    LibraryError,
    LibraryLoadingError,
    PipeDefinitionError,
    PipeLibraryError,
    PipeLoadingError,
)
from pipelex.libraries.library_config import LibraryConfig
from pipelex.libraries.library_manager_abstract import LibraryManagerAbstract
from pipelex.tools.class_registry_utils import ClassRegistryUtils
from pipelex.tools.func_registry_utils import FuncRegistryUtils
from pipelex.tools.misc.file_utils import find_files_in_dir
from pipelex.tools.misc.toml_utils import TOMLValidationError, validate_toml_file
from pipelex.tools.runtime_manager import runtime_manager
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error
from pipelex.types import StrEnum


class LibraryComponent(StrEnum):
    CONCEPT = "concept"
    PIPE = "pipe"

    @property
    def error_class(self) -> type[LibraryError]:
        match self:
            case LibraryComponent.CONCEPT:
                return ConceptLibraryError
            case LibraryComponent.PIPE:
                return PipeLibraryError


class LibraryManager(LibraryManagerAbstract):
    allowed_root_attributes: ClassVar[list[str]] = [
        "domain",
        "definition",
        "system_prompt",
        "system_prompt_jto_structure",
        "prompt_template_to_structure",
    ]

    def __init__(
        self,
        domain_library: DomainLibrary,
        concept_library: ConceptLibrary,
        pipe_library: PipeLibrary,
        library_config: LibraryConfig,
    ):
        self.domain_library = domain_library
        self.concept_library = concept_library
        self.pipe_library = pipe_library
        self.library_config = library_config

    @override
    def validate_libraries(self):
        log.debug("LibraryManager validating libraries")

        self.concept_library.validate_with_libraries()
        self.pipe_library.validate_with_libraries()
        self.domain_library.validate_with_libraries()

    def _validate_toml_files(self):
        """Validate all TOML files used by the library manager for formatting issues."""
        log.debug("LibraryManager validating TOML file formatting")

        # Validation of template paths
        template_paths = self.library_config.get_templates_paths()
        for template_path in template_paths:
            if os.path.exists(template_path):
                try:
                    validate_toml_file(template_path)
                except TOMLValidationError as exc:
                    msg = f"PLX validation failed for template file '{template_path}': {exc}"
                    log.error(msg)
                    raise LibraryError(msg) from exc

    @override
    def setup(self) -> None:
        self.concept_library.setup()

    @override
    def teardown(self) -> None:
        self.pipe_library.teardown()
        self.concept_library.teardown()
        self.domain_library.teardown()

    @override
    def reset(self) -> None:
        self.teardown()
        self.setup()

    def _get_pipeline_library_dirs(self) -> list[Path]:
        library_dirs = [Path(self.library_config.pipelines_dir_path)]
        if runtime_manager.is_unit_testing:
            log.debug("Registering test pipeline structures for unit testing")
            library_dirs += [Path(self.library_config.test_pipelines_dir_path)]
        return library_dirs

    def _get_pipelex_plx_files_from_dirs(self, dirs: list[Path]) -> list[Path]:
        """Get all valid Pipelex PLX files from the given directories."""
        all_plx_paths: list[Path] = []
        for dir_path in dirs:
            if not dir_path.exists():
                msg = f"Directory does not exist: {dir_path}"
                raise LibraryError(msg)

            # Find all TOML files in the directory
            plx_files = find_files_in_dir(
                dir_path=str(dir_path),
                pattern="*.plx",
                is_recursive=True,
            )

            # Filter to only include valid Pipelex files
            for plx_file in plx_files:
                if PipelexInterpreter.is_pipelex_file(plx_file):
                    all_plx_paths.append(plx_file)
                else:
                    log.debug(f"Skipping non-Pipelex PLX file: {plx_file}")

        return all_plx_paths

    @override
    def load_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> list[PipeAbstract]:
        """Load a blueprint."""
        # Create and load domain
        try:
            domain = self._load_domain_from_blueprint(blueprint)
        except DomainDefinitionError as exc:
            msg = f"Could not load domain from PLX blueprint at '{blueprint.source}', domain code: '{blueprint.domain}': {exc}"
            raise DomainLoadingError(message=msg, domain_code=exc.domain_code, description=exc.description, source=exc.source) from exc
        self.domain_library.add_domain(domain=domain)

        # Create and load concepts
        try:
            concepts = self._load_concepts_from_blueprint(blueprint)
        except ConceptDefinitionError as exc:
            msg = f"Could not load concepts from PLX blueprint at '{blueprint.source}', domain code: '{blueprint.domain}': {exc}"
            raise ConceptLoadingError(
                message=msg, concept_definition_error=exc, concept_code=exc.concept_code, description=exc.description, source=exc.source
            ) from exc
        self.concept_library.add_concepts(concepts=concepts)

        # Create and load pipes
        try:
            pipes = self._load_pipes_from_blueprint(blueprint)
        except PipeDefinitionError as exc:
            msg = f"Could not load pipes from PLX blueprint at '{blueprint.source}', domain code: '{blueprint.domain}': {exc}"
            raise PipeLoadingError(
                message=msg, pipe_definition_error=exc, pipe_code=exc.pipe_code or "", description=exc.description or "", source=exc.source
            ) from exc
        self.pipe_library.add_pipes(pipes=pipes)

        return pipes

    @override
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

    def _load_domain_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> Domain:
        return DomainFactory.make_from_blueprint(
            blueprint=DomainBlueprint(
                source=blueprint.source,
                code=blueprint.domain,
                definition=blueprint.definition or "",
                system_prompt=blueprint.system_prompt,
                system_prompt_to_structure=blueprint.system_prompt_to_structure,
                prompt_template_to_structure=blueprint.prompt_template_to_structure,
            ),
        )

    def _load_concepts_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> list[Concept]:
        if blueprint.concept is None:
            return []

        concepts: list[Concept] = []
        for concept_code, concept_blueprint_or_str in blueprint.concept.items():
            concept_blueprint: ConceptBlueprint
            if isinstance(concept_blueprint_or_str, str):
                concept_blueprint = ConceptBlueprint(definition=concept_blueprint_or_str)
            else:
                concept_blueprint = concept_blueprint_or_str
            concept = ConceptFactory.make_from_blueprint(
                domain=blueprint.domain,
                concept_code=concept_code,
                concept_codes_from_the_same_domain=list(blueprint.concept.keys()),
                blueprint=concept_blueprint,
            )
            concepts.append(concept)
        return concepts

    def _load_pipes_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> list[PipeAbstract]:
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

    @override
    def load_libraries(
        self,
        library_dirs: list[Path] | None = None,
        library_file_paths: list[Path] | None = None,
    ) -> None:
        dirs_to_use = library_dirs or self._get_pipeline_library_dirs()

        valid_plx_paths: list[Path]
        if library_file_paths:
            valid_plx_paths = library_file_paths
        else:
            all_plx_paths: list[Path] = self._get_pipelex_plx_files_from_dirs(dirs_to_use)
            # Remove failing pipelines from the list
            failing_pipelines_file_paths = get_config().pipelex.library_config.failing_pipelines_file_paths
            valid_plx_paths = [path for path in all_plx_paths if path not in failing_pipelines_file_paths]

        # Register classes in the directories
        for library_dir in dirs_to_use:
            ClassRegistryUtils.register_classes_in_folder(folder_path=str(library_dir))
            FuncRegistryUtils.register_funcs_in_folder(folder_path=str(library_dir))

        # Parse all blueprints first
        blueprints: list[PipelexBundleBlueprint] = []
        for plx_file_path in valid_plx_paths:
            try:
                blueprint = PipelexInterpreter(file_path=plx_file_path).make_pipelex_bundle_blueprint()
            except FileNotFoundError as exc:
                msg = f"Could not find PLX blueprint at '{plx_file_path}'"
                raise LibraryLoadingError(msg) from exc
            except ValidationError as exc:
                formatted_error_msg = format_pydantic_validation_error(exc)
                msg = f"Could not load PLX blueprint from '{plx_file_path}' because of: {formatted_error_msg}"
                raise LibraryLoadingError(msg) from exc
            except PipeDefinitionError as exc:
                msg = f"Could not load PLX blueprint from '{plx_file_path}': {exc}"
                raise LibraryLoadingError(msg) from exc
            blueprint.source = str(plx_file_path)
            blueprints.append(blueprint)

        # Load all domains first
        all_domains: list[Domain] = []
        for blueprint in blueprints:
            try:
                domain = self._load_domain_from_blueprint(blueprint)
            except DomainDefinitionError as exc:
                msg = f"Could not load domain from PLX blueprint at '{blueprint.source}', domain code: '{blueprint.domain}': {exc}"
                raise LibraryLoadingError(msg) from exc
            all_domains.append(domain)
        self.domain_library.add_domains(domains=all_domains)

        # Load all concepts second
        all_concepts: list[Concept] = []
        for blueprint in blueprints:
            try:
                concepts = self._load_concepts_from_blueprint(blueprint)
            except ConceptDefinitionError as exc:
                msg = f"Could not load concepts from PLX blueprint at '{blueprint.source}', domain code: '{blueprint.domain}': {exc}"
                raise LibraryLoadingError(msg) from exc
            all_concepts.extend(concepts)
        self.concept_library.add_concepts(concepts=all_concepts)

        # Load all pipes third
        all_pipes: list[PipeAbstract] = []
        for blueprint in blueprints:
            try:
                pipes = self._load_pipes_from_blueprint(blueprint)
            except PipeDefinitionError as exc:
                msg = f"Could not load pipes from PLX blueprint at '{blueprint.source}', domain code: '{blueprint.domain}': {exc}"
                raise LibraryLoadingError(msg) from exc
            all_pipes.extend(pipes)
        self.pipe_library.add_pipes(pipes=all_pipes)
