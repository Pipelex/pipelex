import os
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Type

from typing_extensions import override

from pipelex import log
from pipelex.cogt.llm.llm_models.llm_deck import LLMDeck
from pipelex.config import get_config
from pipelex.core.bundle.pipelex_bundle import PipelexBundle
from pipelex.core.bundle.pipelex_bundle_factory import PipelexBundleFactory
from pipelex.core.concept.concept import Concept
from pipelex.core.concept.concept_factory import ConceptFactory
from pipelex.core.concept.concept_library import ConceptLibrary
from pipelex.core.domain.domain import Domain
from pipelex.core.domain.domain_library import DomainLibrary
from pipelex.core.pipe.pipe_abstract import PipeAbstract
from pipelex.core.pipe.pipe_library import PipeLibrary
from pipelex.core.syntax_converter import PipelexSyntaxConverter
from pipelex.exceptions import (
    ConceptLibraryError,
    LibraryError,
    PipeLibraryError,
)
from pipelex.libraries.library_config import LibraryConfig
from pipelex.libraries.library_manager_abstract import LibraryManagerAbstract
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

    def _validate_toml_files(self):
        """Validate all TOML files used by the library manager for formatting issues."""
        log.debug("LibraryManager validating TOML file formatting")

        # Validation of LLM deck paths
        llm_deck_paths = self.library_config.get_llm_deck_paths()
        for llm_deck_path in llm_deck_paths:
            if os.path.exists(llm_deck_path):
                try:
                    validate_toml_file(llm_deck_path)
                except TOMLValidationError as exc:
                    log.error(f"TOML formatting issues in LLM deck file '{llm_deck_path}': {exc}")
                    raise LibraryError(f"TOML validation failed for LLM deck file '{llm_deck_path}': {exc}") from exc

        # Validation of template paths
        template_paths = self.library_config.get_templates_paths()
        for template_path in template_paths:
            if os.path.exists(template_path):
                try:
                    validate_toml_file(template_path)
                except TOMLValidationError as exc:
                    log.error(f"TOML formatting issues in template file '{template_path}': {exc}")
                    raise LibraryError(f"TOML validation failed for template file '{template_path}': {exc}") from exc

    @override
    def setup(self) -> None:
        self.load_libraries()

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

    def _get_pipeline_library_paths(self) -> List[Path]:
        library_paths = [self.library_config.pipelines_path]
        toml_file_paths = self._list_toml_files_from_path(library_paths=[Path(path) for path in library_paths])

        # Remove failing_pipelines_path from the list
        failing_pipelines_path = get_config().pipelex.library_config.failing_pipelines_path
        toml_file_paths = [path for path in toml_file_paths if path != Path(failing_pipelines_path)]

        if runtime_manager.is_unit_testing:
            log.debug("Registering test pipeline structures for unit testing")
            library_paths += [self.library_config.test_pipelines_path]
        return [Path(path) for path in library_paths]

    def _list_toml_files_from_path(self, library_paths: List[Path]) -> List[Path]:
        toml_file_paths: List[Path] = []
        for libraries_path in library_paths:
            # Use the existing utility function specifically for TOML files
            found_file_paths = find_files_in_dir(
                dir_path=str(libraries_path),
                pattern="*.toml",
                is_recursive=True,
            )
            log.debug(f"Searching for TOML files in {libraries_path}, found '{found_file_paths}'")
            if not found_file_paths:
                log.warning(f"No TOML files found in library path: {libraries_path}")
            toml_file_paths.extend(found_file_paths)
        return toml_file_paths

    def load_from_file(self, toml_path: Path):
        converter = PipelexSyntaxConverter(file_path=toml_path)
        blueprint = converter.make_pipelex_bundle_blueprint()
        pipelex_bundle = PipelexBundleFactory.make_from_blueprint(blueprint=blueprint)
        self.load_from_pipelex_bundle(pipelex_bundle=pipelex_bundle)

    def load_from_pipelex_bundle(self, pipelex_bundle: PipelexBundle):
        self.domain_library.add_domain(domain=pipelex_bundle.domain)
        self.concept_library.add_concepts(concepts=list(pipelex_bundle.concepts.values()))
        self.pipe_library.add_pipes(pipes=list(pipelex_bundle.pipes.values()))

    @override
    def load_libraries(self, library_paths: Optional[List[Path]] = None):
        self.load_deck()
        library_paths = library_paths or self._get_pipeline_library_paths()
        for library_path in library_paths:
            toml_file_paths = self._list_toml_files_from_path(library_paths=[library_path])
            for toml_file_path in toml_file_paths:
                self.load_from_file(toml_path=toml_file_path)

    # Todo: move to LLMDeckManager
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

    def load_domain(self, domain: Domain) -> Domain:
        self.domain_library.add_domain(domain=domain)
        return domain

    def load_concepts(self, concepts: List[Concept]) -> List[Concept]:
        """Load concepts from a validated blueprint."""
        native_concepts = ConceptFactory.list_native_concepts()
        self.concept_library.add_concepts(concepts=native_concepts)
        for concept in concepts:
            self.concept_library.add_new_concept(concept=concept)
        return concepts

    def load_pipes(self, pipes: List[PipeAbstract]) -> List[PipeAbstract]:
        """Load pipes from a validated blueprint."""
        for pipe in pipes:
            self.pipe_library.add_pipe(pipe=pipe)

        return pipes
