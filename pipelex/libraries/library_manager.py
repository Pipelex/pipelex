import os
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Type

from typing_extensions import override

from pipelex import log
from pipelex.cogt.llm.llm_models.llm_deck import LLMDeck
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
    ConceptLibraryError,
    LibraryError,
    PipeLibraryError,
)
from pipelex.libraries.library_config import LibraryConfig
from pipelex.libraries.library_manager_abstract import LibraryManagerAbstract
from pipelex.tools.class_registry_utils import ClassRegistryUtils
from pipelex.tools.misc.file_utils import find_files_in_dir
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import TOMLValidationError, load_toml_from_path, validate_toml_file
from pipelex.tools.runtime_manager import runtime_manager
from pipelex.types import StrEnum


class LLMDeckNotFoundError(LibraryError):
    pass


class LibraryComponent(StrEnum):
    CONCEPT = "concept"
    PIPE = "pipe"

    @property
    def error_class(self) -> Type[LibraryError]:
        match self:
            case LibraryComponent.CONCEPT:
                return ConceptLibraryError
            case LibraryComponent.PIPE:
                return PipeLibraryError


class LibraryManager(LibraryManagerAbstract):
    allowed_root_attributes: ClassVar[List[str]] = [
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
        self.llm_deck: Optional[LLMDeck] = None

    @override
    def validate_libraries(self):
        log.debug("LibraryManager validating libraries")

        if self.llm_deck is None:
            raise LibraryError("LLM deck is not loaded")

        self.llm_deck.validate_llm_presets()
        LLMDeck.final_validate(deck=self.llm_deck)
        self.concept_library.validate_with_libraries()
        self.pipe_library.validate_with_libraries()
        self.domain_library.validate_with_libraries()

    def _validate_plx_files(self):
        """Validate all PLX files used by the library manager for formatting issues."""
        log.debug("LibraryManager validating PLX file formatting")

        # Validation of LLM deck paths
        llm_deck_paths = self.library_config.get_llm_deck_paths()
        for llm_deck_path in llm_deck_paths:
            if os.path.exists(llm_deck_path):
                try:
                    validate_toml_file(llm_deck_path)
                except TOMLValidationError as exc:
                    log.error(f"PLX formatting issues in LLM deck file '{llm_deck_path}': {exc}")
                    raise LibraryError(f"PLX validation failed for LLM deck file '{llm_deck_path}': {exc}") from exc

        # Validation of template paths
        template_paths = self.library_config.get_templates_paths()
        for template_path in template_paths:
            if os.path.exists(template_path):
                try:
                    validate_toml_file(template_path)
                except TOMLValidationError as exc:
                    log.error(f"PLX formatting issues in template file '{template_path}': {exc}")
                    raise LibraryError(f"PLX validation failed for template file '{template_path}': {exc}") from exc

    @override
    def setup(self) -> None:
        self.concept_library.setup()

    @override
    def teardown(self) -> None:
        self.llm_deck = None
        self.pipe_library.teardown()
        self.concept_library.teardown()
        self.domain_library.teardown()

    @override
    def reset(self) -> None:
        self.teardown()
        self.setup()

    def _get_pipeline_library_dirs(self) -> List[Path]:
        library_dirs = [Path(self.library_config.pipelines_dir_path)]
        if runtime_manager.is_unit_testing:
            log.debug("Registering test pipeline structures for unit testing")
            library_dirs += [Path(self.library_config.test_pipelines_dir_path)]
        return library_dirs

    def _get_pipelex_plx_files_from_dirs(self, dirs: List[Path]) -> List[Path]:
        """Get all valid Pipelex PLX files from the given directories."""

        all_plx_paths: List[Path] = []
        for dir_path in dirs:
            if not dir_path.exists():
                raise LibraryError(f"Directory does not exist: {dir_path}")

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
    def load_from_file(self, plx_path: Path) -> None:
        """Load a single file - this method is kept for compatibility."""
        if not PipelexInterpreter.is_pipelex_file(plx_path):
            raise LibraryError(f"File is not a valid Pipelex PLX file: {plx_path}")

        blueprint = PipelexInterpreter(file_path=plx_path).make_pipelex_bundle_blueprint()
        self.load_from_blueprint(blueprint)

    @override
    def load_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> List[PipeAbstract]:
        """Load a blueprint."""
        # Create and load domain
        domain = self._load_domain_from_blueprint(blueprint)
        self.domain_library.add_domain(domain=domain)

        # Create and load concepts
        concepts = self._load_concepts_from_blueprint(blueprint)
        self.concept_library.add_concepts(concepts=concepts)

        # Create and load pipes
        pipes = self._load_pipes_from_blueprint(blueprint)
        self.pipe_library.add_pipes(pipes=pipes)

        return pipes

    def _load_domain_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> Domain:
        """Create a Domain from blueprint."""
        return DomainFactory.make_from_blueprint(
            blueprint=DomainBlueprint(
                code=blueprint.domain,
                definition=blueprint.definition,
                system_prompt=blueprint.system_prompt,
                system_prompt_to_structure=blueprint.system_prompt_to_structure,
                prompt_template_to_structure=blueprint.prompt_template_to_structure,
            )
        )

    def _load_concepts_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> List[Concept]:
        """Create Concepts from blueprint."""
        concepts: List[Concept] = []

        if blueprint.concept is not None:
            for concept_code, concept_blueprint_or_str in blueprint.concept.items():
                concept = ConceptFactory.make_from_blueprint(
                    domain=blueprint.domain,
                    concept_code=concept_code,
                    concept_codes_from_the_same_domain=list(blueprint.concept.keys()),
                    blueprint=ConceptBlueprint(definition=concept_blueprint_or_str)
                    if isinstance(concept_blueprint_or_str, str)
                    else concept_blueprint_or_str,
                )
                concepts.append(concept)
        return concepts

    def _load_pipes_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> List[PipeAbstract]:
        """Create Pipes from blueprint."""
        pipes: List[PipeAbstract] = []
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
    def load_libraries(self, library_dirs: Optional[List[Path]] = None, library_file_paths: Optional[List[Path]] = None) -> None:
        dirs_to_use: List[Path] = self._get_pipeline_library_dirs()
        all_plx_paths: List[Path] = self._get_pipelex_plx_files_from_dirs(dirs_to_use)

        # Remove failing pipelines from the list
        failing_pipelines_file_paths = get_config().pipelex.library_config.failing_pipelines_file_paths
        failing_paths_set = {Path(fp) for fp in failing_pipelines_file_paths}
        all_plx_paths = [path for path in all_plx_paths if path not in failing_paths_set]

        if library_dirs is not None:
            dirs_to_use = library_dirs

        # Register classes in the directories
        for library_dir in dirs_to_use:
            ClassRegistryUtils.register_classes_in_folder(folder_path=str(library_dir))

        if library_file_paths is not None:
            all_plx_paths = library_file_paths

        # Parse all blueprints first
        blueprints: List[PipelexBundleBlueprint] = []
        for plx_file_path in all_plx_paths:
            blueprint = PipelexInterpreter(file_path=plx_file_path).make_pipelex_bundle_blueprint()
            blueprints.append(blueprint)

        # Load all domains first
        all_domains: List[Domain] = []
        for blueprint in blueprints:
            domain = self._load_domain_from_blueprint(blueprint)
            all_domains.append(domain)
        for domain in all_domains:
            self.domain_library.add_domain(domain=domain)

        # Load all concepts second
        all_concepts: List[Concept] = []
        for blueprint in blueprints:
            concepts = self._load_concepts_from_blueprint(blueprint)
            all_concepts.extend(concepts)
        self.concept_library.add_concepts(concepts=all_concepts)

        # Load all pipes third
        all_pipes: List[PipeAbstract] = []
        for blueprint in blueprints:
            pipes = self._load_pipes_from_blueprint(blueprint)
            all_pipes.extend(pipes)
        self.pipe_library.add_pipes(pipes=all_pipes)

    # TODO: move to LLMDeckManager
    def load_deck(self) -> LLMDeck:
        llm_deck_paths = self.library_config.get_llm_deck_paths()
        full_llm_deck_dict: Dict[str, Any] = {}
        if not llm_deck_paths:
            raise LLMDeckNotFoundError("No LLM deck paths found. Please run `pipelex init-libraries` to create it.")

        for llm_deck_path in llm_deck_paths:
            if not os.path.exists(llm_deck_path):
                raise LLMDeckNotFoundError(f"LLM deck path `{llm_deck_path}` not found. Please run `pipelex init-libraries` to create it.")
            try:
                llm_deck_dict = load_toml_from_path(path=llm_deck_path)
                log.debug(f"Loaded LLM deck from {llm_deck_path}")
                deep_update(full_llm_deck_dict, llm_deck_dict)
            except Exception as exc:
                log.error(f"Failed to load LLM deck file '{llm_deck_path}': {exc}")
                raise

        self.llm_deck = LLMDeck.model_validate(full_llm_deck_dict)
        return self.llm_deck
