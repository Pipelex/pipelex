import os
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Type

from kajson.exceptions import ClassRegistryInheritanceError, ClassRegistryNotFoundError
from kajson.kajson_manager import KajsonManager
from pydantic import ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.cogt.llm.llm_models.llm_deck import LLMDeck
from pipelex.config import get_config
from pipelex.core.concept_factory import ConceptFactory
from pipelex.core.concept_library import ConceptLibrary
from pipelex.core.domain import Domain
from pipelex.core.domain_library import DomainLibrary
from pipelex.core.pipe_abstract import PipeAbstract
from pipelex.core.pipe_blueprint import PipeSpecificFactoryProtocol
from pipelex.core.pipe_library import PipeLibrary
from pipelex.exceptions import (
    ConceptLibraryError,
    LibraryError,
    LibraryParsingError,
    PipeFactoryError,
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
        "system_prompt_to_structure",
        "prompt_template_to_structure",
    ]
    domain_library: DomainLibrary
    concept_library: ConceptLibrary
    pipe_library: PipeLibrary
    llm_deck: Optional[LLMDeck] = None
    library_config: ClassVar[LibraryConfig]

    @classmethod
    def make_empty(cls, config_folder_path: str) -> "LibraryManager":
        cls.domain_library = DomainLibrary.make_empty()
        cls.concept_library = ConceptLibrary.make_empty()
        cls.pipe_library = PipeLibrary.make_empty()
        cls.library_config = LibraryConfig(config_folder_path=config_folder_path)
        return cls()

    @classmethod
    def make(
        cls, domain_library: DomainLibrary, concept_library: ConceptLibrary, pipe_library: PipeLibrary, config_folder_path: str
    ) -> "LibraryManager":
        cls.domain_library = domain_library
        cls.concept_library = concept_library
        cls.pipe_library = pipe_library
        cls.library_config = LibraryConfig(config_folder_path=config_folder_path)
        return cls()

    @override
    def get_plugin_config_path(self) -> str:
        return self.library_config.get_default_plugin_config_path()

    @override
    def setup(self) -> None:
        pass

    @override
    def teardown(self) -> None:
        self.llm_deck = None
        self.pipe_library.teardown()
        self.concept_library.teardown()
        self.domain_library.teardown()

    def libraries_paths(self) -> List[str]:
        library_paths = [self.library_config.pipelines_path]
        if runtime_manager.is_unit_testing:
            log.debug("Registering test pipeline structures for unit testing")
            library_paths += [self.library_config.test_pipelines_path]
        return library_paths

    def load_failure_modes(self):
        failing_pipelines_path = get_config().pipelex.library_config.failing_pipelines_path
        self.load_combo_libraries(library_paths=[Path(failing_pipelines_path)])

    def load_libraries(self):
        log.debug("LibraryManager loading separate libraries")
        library_paths = self.libraries_paths()
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

    @override
    def load_combo_libraries(self, library_paths: List[Path]):
        log.debug("LibraryManager loading combo libraries")
        # Find all .toml files in the directories and their subdirectories

        # First pass: load all domains
        for toml_path in library_paths:
            library_dict = load_toml_from_path(path=str(toml_path))
            library_name = toml_path.stem
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

        # Second pass: load all concepts
        for toml_path in library_paths:
            nb_concepts_before = len(self.concept_library.root)
            library_dict = load_toml_from_path(path=str(toml_path))
            library_name = toml_path.stem
            try:
                self._load_library_dict(library_name=library_name, library_dict=library_dict, component_type=LibraryComponent.CONCEPT)
            except ConceptLibraryError as exc:
                raise LibraryError(f"Error loading concepts from library '{library_name}' at '{toml_path}': {exc}") from exc
            nb_concepts_loaded = len(self.concept_library.root) - nb_concepts_before
            log.verbose(f"Loaded {nb_concepts_loaded} concepts from '{toml_path.name}'")

        # Third pass: load all pipes
        for toml_path in library_paths:
            nb_pipes_before = len(self.pipe_library.root)
            try:
                library_dict = load_toml_from_path(path=str(toml_path))
            except Exception as exc:
                log.error(f"Failed to load TOML file '{toml_path}': {exc}")
                continue
            library_name = toml_path.stem
            try:
                self._load_library_dict(library_name=library_name, library_dict=library_dict, component_type=LibraryComponent.PIPE)
            except StaticValidationError as static_validation_error:
                static_validation_error.file_path = str(toml_path)
                log.error(static_validation_error.desc())
                raise static_validation_error
            except PipeLibraryError as pipe_library_error:
                raise LibraryError(
                    f"Error loading pipes from library '{library_name}' at '{toml_path}': {pipe_library_error}"
                ) from pipe_library_error
            nb_pipes_loaded = len(self.pipe_library.root) - nb_pipes_before
            log.verbose(f"Loaded {nb_pipes_loaded} pipes from '{toml_path.name}'")

    def _load_library_dict(self, library_name: str, library_dict: Dict[str, Any], component_type: LibraryComponent):
        if domain_code := library_dict.pop("domain", None):
            # domain is set at the root of the library
            self._load_library_components_from_recursive_dict(
                domain_code=domain_code,
                recursive_dict=library_dict,
                component_type=component_type,
            )
        else:
            raise LibraryParsingError(f"Library '{library_name}' has no domain set")

    def _load_library_components_from_recursive_dict(
        self,
        domain_code: str,
        recursive_dict: Dict[str, Any],
        component_type: LibraryComponent,
    ):
        for key, obj in recursive_dict.items():
            # root of domain
            if not isinstance(obj, dict):
                if not isinstance(obj, str):
                    raise LibraryError(f"Only a dict or a string is expected at the root of domain but '{domain_code}' got type '{type(obj)}'")
                if key not in self.allowed_root_attributes:
                    raise LibraryParsingError(f"Domain '{domain_code}' has an unexpected root attribute '{key}'")
                continue

            # definitions within the domain
            obj_dict: Dict[str, Any] = obj
            if key == component_type:
                if key == LibraryComponent.CONCEPT:
                    self._load_concepts(domain_code=domain_code, obj_dict=obj_dict)
                elif key == LibraryComponent.PIPE:
                    self._load_pipes(domain_code=domain_code, obj_dict=obj_dict)
                else:
                    continue
            elif key not in [LibraryComponent.CONCEPT, LibraryComponent.PIPE]:
                # Not a concept but a subdomain
                self._load_library_components_from_recursive_dict(domain_code=domain_code, recursive_dict=obj_dict, component_type=component_type)
            else:
                # Skip keys that don't match our criteria
                continue

    def _load_concepts(self, domain_code: str, obj_dict: Dict[str, Any]):
        for concept_str, concept_obj in obj_dict.items():
            if isinstance(concept_obj, str):
                # we only have a definition
                definition = concept_obj
                concept_from_def = ConceptFactory.make_concept_from_definition_str(
                    domain_code=domain_code,
                    concept_str=concept_str,
                    definition=definition,
                )
                self.concept_library.add_new_concept(concept=concept_from_def)
            elif isinstance(concept_obj, dict):
                # blueprint dict definition
                concept_obj_dict: Dict[str, Any] = concept_obj
                try:
                    concept_from_dict = ConceptFactory.make_from_details_dict(
                        domain_code=domain_code, code=concept_str, details_dict=concept_obj_dict
                    )
                except ValidationError as exc:
                    error_msg = format_pydantic_validation_error(exc)
                    raise ConceptLibraryError(f"Error loading concept '{concept_str}' because of: {error_msg}") from exc
                self.concept_library.add_new_concept(concept=concept_from_dict)
            else:
                raise ConceptLibraryError(f"Unexpected type for concept_code '{concept_str}' in domain '{domain_code}': {type(concept_obj)}")

    def _load_pipes(self, domain_code: str, obj_dict: Dict[str, Any]):
        for pipe_code, pipe_obj in obj_dict.items():
            if isinstance(pipe_obj, str):
                # TODO: handle one-liner
                pass
            elif isinstance(pipe_obj, dict):
                pipe_obj_dict: Dict[str, Any] = pipe_obj.copy()
                try:
                    pipe = LibraryManager.make_pipe_from_details_dict(
                        domain_code=domain_code,
                        pipe_code=pipe_code,
                        details_dict=pipe_obj_dict,
                    )
                except ValidationError as exc:
                    error_msg = format_pydantic_validation_error(exc)
                    raise PipeLibraryError(f"Error loading pipe '{pipe_code}' because of: {error_msg}") from exc
                self.pipe_library.add_new_pipe(pipe=pipe)

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
        library_paths = self.libraries_paths()
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

    @classmethod
    def make_pipe_from_details_dict(
        cls,
        domain_code: str,
        pipe_code: str,
        details_dict: Dict[str, Any],
    ) -> PipeAbstract:
        # first line in the details_dict is the pipe definition in the format:
        # PipeClassName = "the pipe's definition in natural language"
        pipe_definition: str
        pipe_class_name: str
        try:
            pipe_class_name, pipe_definition = next(iter(details_dict.items()))
            details_dict.pop(pipe_class_name)
        except StopIteration as details_dict_empty_error:
            raise PipeFactoryError(f"Pipe '{pipe_code}' could not be created because its blueprint is empty.") from details_dict_empty_error

        # the factory class name for that specific type of Pipe is the pipe class name with "Factory" suffix
        factory_class_name = f"{pipe_class_name}Factory"
        try:
            pipe_factory: Type[PipeSpecificFactoryProtocol[Any, Any]] = KajsonManager.get_class_registry().get_required_subclass(
                name=factory_class_name,
                base_class=PipeSpecificFactoryProtocol,
            )
        except ClassRegistryNotFoundError as factory_not_found_error:
            raise PipeFactoryError(
                f"Pipe '{pipe_code}' couldn't be created: factory '{factory_class_name}' not found: {factory_not_found_error}"
            ) from factory_not_found_error
        except ClassRegistryInheritanceError as factory_inheritance_error:
            raise PipeFactoryError(
                f"Pipe '{pipe_code}' couldn't be created: factory '{factory_class_name}' is not a subclass of {type(PipeSpecificFactoryProtocol)}."
            ) from factory_inheritance_error

        details_dict["definition"] = pipe_definition
        details_dict["domain"] = domain_code
        pipe_from_blueprint: PipeAbstract = pipe_factory.make_pipe_from_details_dict(
            domain_code=domain_code,
            pipe_code=pipe_code,
            details_dict=details_dict,
        )
        return pipe_from_blueprint
