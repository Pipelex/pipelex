import os
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional

from pydantic import ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.cogt.llm.llm_models.llm_deck import LLMDeck
from pipelex.config import get_config
from pipelex.core.concept_factory import ConceptFactory
from pipelex.core.concept_library import ConceptLibrary
from pipelex.core.domain import Domain
from pipelex.core.domain_library import DomainLibrary
from pipelex.core.pipe_factory import PipeFactory
from pipelex.core.pipe_library import PipeLibrary
from pipelex.exceptions import (
    ConceptLibraryError,
    LibraryError,
    LibraryParsingError,
    PipeLibraryError,
    StaticValidationError,
)
from pipelex.libraries.library_config import LibraryConfig
from pipelex.libraries.library_manager_abstract import LibraryManagerAbstract
from pipelex.tools.class_registry_utils import ClassRegistryUtils
from pipelex.tools.misc.file_utils import find_files_in_dir
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import TOMLValidationError, load_toml_from_path, validate_toml_file
from pipelex.tools.runtime_manager import runtime_manager
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error
from pipelex.types import StrEnum


class LLMDeckNotFoundError(LibraryError):
    pass


class LibraryComponent(StrEnum):
    CONCEPT = "concept"
    PIPE = "pipe"
    DOMAIN = "domain"


class LibraryManager(LibraryManagerAbstract):
    allowed_root_attributes: ClassVar[List[str]] = [
        "domain",
        "definition",
        "system_prompt",
        "system_prompt_to_structure",
        "prompt_template_to_structure",
    ]
    domain_library: DomainLibrary
    concept_library: ConceptLibrary
    pipe_library: PipeLibrary
    llm_deck: Optional[LLMDeck] = None
    library_config: ClassVar[LibraryConfig]

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

        llm_deck_paths = self.library_config.get_llm_deck_paths()
        for llm_deck_path in llm_deck_paths:
            if os.path.exists(llm_deck_path):
                try:
                    validate_toml_file(llm_deck_path)
                except TOMLValidationError as exc:
                    log.error(f"TOML formatting issues in LLM deck file '{llm_deck_path}': {exc}")
                    raise LibraryError(f"TOML validation failed for LLM deck file '{llm_deck_path}': {exc}") from exc

        # Validate pipeline library TOML files (same pattern as _load_combo_libraries)
        library_paths = self.get_libraries_paths()
        toml_file_paths: List[Path] = []
        for libraries_path in library_paths:
            if os.path.exists(libraries_path):
                found_file_paths = find_files_in_dir(
                    dir_path=libraries_path,
                    pattern="*.toml",
                    is_recursive=True,
                )
                toml_file_paths.extend(found_file_paths)

        for toml_path in toml_file_paths:
            try:
                validate_toml_file(str(toml_path))
            except TOMLValidationError as exc:
                log.error(f"TOML formatting issues in library file '{toml_path}': {exc}")
                raise LibraryError(f"TOML validation failed for library file '{toml_path}': {exc}") from exc

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
        pass

    @override
    def teardown(self) -> None:
        self.llm_deck = None
        self.pipe_library.teardown()
        self.concept_library.teardown()
        self.domain_library.teardown()

    def get_libraries_paths(self) -> List[str]:
        library_paths = [self.library_config.pipelines_path]
        if runtime_manager.is_unit_testing:
            log.debug("Registering test pipeline structures for unit testing")
            library_paths += [self.library_config.test_pipelines_path]
        return library_paths

    def get_library_dict_from_path(self, library_path: Path) -> Dict[str, Any]:
        return load_toml_from_path(path=str(library_path))

    def load_failure_modes(self):
        failing_pipelines_path = get_config().pipelex.library_config.failing_pipelines_path
        self.load_combo_libraries(library_paths=[Path(failing_pipelines_path)])

    def load_libraries(self):
        log.debug("LibraryManager loading separate libraries")
        library_paths = self.get_libraries_paths()
        # self._validate_toml_files()
        for library_path in library_paths:
            ClassRegistryUtils.register_classes_in_folder(
                folder_path=library_path,
            )

        native_concepts = ConceptFactory.list_native_concepts()
        self.concept_library.add_concepts(concepts=native_concepts)

        toml_file_paths = self.list_toml_files_from_path(library_paths=library_paths)
        # remove failing_pipelines_path from the list
        failing_pipelines_path = get_config().pipelex.library_config.failing_pipelines_path
        toml_file_paths = [path for path in toml_file_paths if path != Path(failing_pipelines_path)]
        self.load_combo_libraries(library_paths=toml_file_paths)

    @override
    def load_combo_libraries(self, library_paths: List[Path]):
        log.debug("LibraryManager loading combo libraries")

        # 1. Load domains
        self.load_domains(library_paths)
        # 2. Load concepts
        self.load_concepts(library_paths)
        # 3. Load pipes
        self.load_pipes(library_paths)

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

    def list_toml_files_from_path(self, library_paths: List[str]) -> List[Path]:
        toml_file_paths: List[Path] = []
        for libraries_path in library_paths:
            # Use the existing utility function specifically for TOML files
            found_file_paths = find_files_in_dir(
                dir_path=libraries_path,
                pattern="*.toml",
                is_recursive=True,
            )
            log.debug(f"Searching for TOML files in {libraries_path}, found '{found_file_paths}'")
            if not found_file_paths:
                log.warning(f"No TOML files found in library path: {libraries_path}")
            toml_file_paths.extend(found_file_paths)
        return toml_file_paths

    def load_domains(self, library_paths: List[Path]):
        """Load all domains from the provided library paths."""
        log.debug("Loading domains from libraries")
        for toml_path in library_paths:
            library_name, library_dict = toml_path.stem, self.get_library_dict_from_path(library_path=toml_path)
            domain_code = library_dict.get("domain")
            if domain_code is None:
                raise LibraryParsingError(
                    f"Error loading library '{library_name}' which has no domain set at '{toml_path}'. "
                    "Just write 'domain = \"my_domain\"' at the top of the file."
                )
            domain_definition = library_dict.get("definition")
            system_prompt = library_dict.get("system_prompt")
            system_prompt_to_structure = library_dict.get("system_prompt_to_structure")
            prompt_template_to_structure = library_dict.get("prompt_template_to_structure")
            domain = Domain(
                code=domain_code,
                definition=domain_definition,
                system_prompt=system_prompt,
                system_prompt_to_structure=system_prompt_to_structure,
                prompt_template_to_structure=prompt_template_to_structure,
            )
            self.domain_library.add_domain_details(domain=domain)

    def load_concepts(self, library_paths: List[Path]):
        """Load all concepts from the provided library paths."""
        log.debug("Loading concepts from libraries...")

        for toml_path in library_paths:
            library_name, library_dict = toml_path.stem, self.get_library_dict_from_path(library_path=toml_path)
            domain_code = library_dict.get("domain")

            if domain_code is None:
                raise LibraryParsingError(f"Library '{library_name}' has no domain set")

            concepts_dict: Dict[str, Any] = library_dict.get(LibraryComponent.CONCEPT, {})
            if not concepts_dict:
                continue

            for concept_str, concept_obj in concepts_dict.items():
                log.debug(f"Loading concept '{concept_str}' from '{library_name}' in '{toml_path}'...")
                try:
                    if isinstance(concept_obj, str):
                        # Simple definition: ConceptName = "description"
                        concept = ConceptFactory.make_concept_from_definition_str(
                            domain_code=domain_code,
                            concept_str=concept_str,
                            definition=concept_obj,
                        )
                        self.concept_library.add_new_concept(concept=concept)
                    elif isinstance(concept_obj, dict):
                        # Detailed definition: [concept.ConceptName] with fields
                        concept_obj_dict: Dict[str, Any] = concept_obj
                        concept = ConceptFactory.make_from_details_dict(domain_code=domain_code, code=concept_str, details_dict=concept_obj_dict)
                        self.concept_library.add_new_concept(concept=concept)
                    else:
                        raise ConceptLibraryError(f"Unexpected type for concept '{concept_str}': {type(concept_obj)}")
                except ValidationError as exc:
                    error_msg = format_pydantic_validation_error(exc)
                    raise LibraryError(f"Error loading concept '{concept_str}' from '{library_name}': {error_msg}") from exc
                except ConceptLibraryError as exc:
                    raise LibraryError(f"Error loading concepts from library '{library_name}' at '{toml_path}': {exc}") from exc

    def load_pipes(self, library_paths: List[Path]):
        """Load all pipes from the provided library paths."""
        log.debug("Loading pipes from libraries...")

        for toml_path in library_paths:
            library_name, library_dict = toml_path.stem, self.get_library_dict_from_path(library_path=toml_path)

            domain_code = library_dict.get("domain")
            if domain_code is None:
                raise LibraryParsingError(f"Library '{library_name}' has no domain set")

            pipes_dict = library_dict.get(LibraryComponent.PIPE, {})
            if not pipes_dict:
                continue

            for pipe_code, pipe_obj in pipes_dict.items():
                if isinstance(pipe_obj, str):
                    # TODO: handle one-liner pipes
                    pass
                elif isinstance(pipe_obj, dict):
                    pipe_obj_dict: Dict[str, Any] = pipe_obj.copy()
                    try:
                        pipe = PipeFactory.make_pipe_from_details_dict(
                            domain_code=domain_code,
                            pipe_code=pipe_code,
                            details_dict=pipe_obj_dict,
                        )
                        self.pipe_library.add_new_pipe(pipe=pipe)
                    except ValidationError as exc:
                        error_msg = format_pydantic_validation_error(exc)
                        raise PipeLibraryError(f"Error loading pipe '{pipe_code}': {error_msg}") from exc
                    except StaticValidationError as static_validation_error:
                        static_validation_error.file_path = str(toml_path)
                        log.error(static_validation_error.desc())
                        raise static_validation_error
                    except PipeLibraryError as pipe_library_error:
                        raise LibraryError(
                            f"Error loading pipes from library '{library_name}' at '{toml_path}': {pipe_library_error}"
                        ) from pipe_library_error
