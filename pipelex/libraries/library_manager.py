import importlib
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
from pipelex.core.pipe_blueprint import PipeBlueprint, PipeSpecificFactoryProtocol
from pipelex.core.pipe_library import PipeLibrary
from pipelex.exceptions import (
    ConceptLibraryError,
    LibraryError,
    PipeFactoryError,
    PipeLibraryError,
    StaticValidationError,
)
from pipelex.libraries.library_config import LibraryConfig
from pipelex.libraries.library_manager_abstract import LibraryManagerAbstract
from pipelex.libraries.pipeline_blueprint import (
    ConceptBlueprintError,
    PipeBlueprintError,
    PipelineBlueprint,
    PipelineBlueprintValidationError,
)
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
            blueprint = self._load_blueprint_from_file(toml_path)
            domain = Domain(
                code=blueprint.domain,
                definition=blueprint.definition,
                system_prompt=blueprint.system_prompt,
                system_prompt_to_structure=blueprint.system_prompt_to_structure,
                prompt_template_to_structure=blueprint.prompt_template_to_structure,
            )
            self.domain_library.add_domain_details(domain=domain)

        # Second pass: load all concepts
        for toml_path in library_paths:
            nb_concepts_before = len(self.concept_library.root)
            blueprint = self._load_blueprint_from_file(toml_path)
            self._load_concepts_from_blueprint(blueprint=blueprint, file_path=str(toml_path))
            nb_concepts_loaded = len(self.concept_library.root) - nb_concepts_before
            log.verbose(f"Loaded {nb_concepts_loaded} concepts from '{toml_path.name}'")

        # Third pass: load all pipes
        for toml_path in library_paths:
            nb_pipes_before = len(self.pipe_library.root)
            blueprint = self._load_blueprint_from_file(toml_path)
            self._load_pipes_from_blueprint(blueprint=blueprint, file_path=str(toml_path))
            nb_pipes_loaded = len(self.pipe_library.root) - nb_pipes_before
            log.verbose(f"Loaded {nb_pipes_loaded} pipes from '{toml_path.name}'")

    def _load_blueprint_from_file(self, toml_path: Path) -> PipelineBlueprint:
        """Load and validate a pipeline blueprint from a TOML file."""
        try:
            toml_data = load_toml_from_path(path=str(toml_path))
            blueprint = PipelineBlueprint.model_validate(toml_data)
            return blueprint
        except ValidationError as exc:
            error_msg = format_pydantic_validation_error(exc)
            raise PipelineBlueprintValidationError(
                file_path=str(toml_path),
                validation_error_msg=error_msg,
            ) from exc
        except Exception as exc:
            raise LibraryError(f"Failed to load TOML file '{toml_path}': {exc}") from exc

    def _load_concepts_from_blueprint(self, blueprint: PipelineBlueprint, file_path: str):
        """Load concepts from a validated blueprint."""
        for concept_name, concept_data in blueprint.concept.items():
            try:
                if isinstance(concept_data, str):
                    # Simple string definition
                    concept_from_def = ConceptFactory.make_concept_from_definition_str(
                        domain_code=blueprint.domain,
                        concept_str=concept_name,
                        definition=concept_data,
                    )
                    self.concept_library.add_new_concept(concept=concept_from_def)
                else:
                    # Complex ConceptBlueprint - guaranteed by blueprint schema
                    concept_from_blueprint = ConceptFactory.make_concept_from_blueprint(
                        domain=blueprint.domain,
                        code=concept_name,
                        concept_blueprint=concept_data,
                    )
                    self.concept_library.add_new_concept(concept=concept_from_blueprint)
            except ValidationError as exc:
                error_msg = format_pydantic_validation_error(exc)
                raise ConceptBlueprintError(
                    file_path=file_path,
                    concept_name=concept_name,
                    error_msg=error_msg,
                ) from exc

    def _load_pipes_from_blueprint(self, blueprint: PipelineBlueprint, file_path: str):
        """Load pipes from a validated blueprint."""
        for pipe_name, pipe_data in blueprint.pipe.items():
            try:
                # pipe_data is guaranteed to be Dict[str, Any] by the blueprint schema
                pipe = LibraryManager.make_pipe_from_blueprint(
                    domain_code=blueprint.domain,
                    pipe_code=pipe_name,
                    details_dict=pipe_data.copy(),
                )
                self.pipe_library.add_new_pipe(pipe=pipe)
            except ValidationError as validation_error:
                error_msg = format_pydantic_validation_error(validation_error)
                raise PipeBlueprintError(
                    file_path=file_path,
                    pipe_name=pipe_name,
                    error_msg=error_msg,
                ) from validation_error
            except StaticValidationError as static_validation_error:
                static_validation_error.file_path = file_path
                raise static_validation_error

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
    def make_pipe_from_blueprint(
        cls,
        domain_code: str,
        pipe_code: str,
        details_dict: Dict[str, Any],
    ) -> PipeAbstract:
        pipe_definition: str
        pipe_class_name: str
        if "type" in details_dict and "definition" in details_dict:
            # New format: type = "PipeClassName" and definition = "description"
            pipe_class_name = details_dict.pop("type")  # Remove type from details_dict
            pipe_definition = details_dict["definition"]  # Keep definition for the factory
        else:
            # TODO(DEPRECATED_REMOVAL): Remove old pipe syntax support - scheduled for removal in v0.3.0
            # Fallback to old format for backward compatibility:
            # PipeClassName = "the pipe's definition in natural language"
            try:
                pipe_class_name, pipe_definition = next(iter(details_dict.items()))
                log.warning(f"""Pipe '{pipe_code}' uses deprecated syntax. Please migrate to new format:
replace this syntax:
```
{pipe_class_name} = "{pipe_definition}"
```
by this:
```
type = "{pipe_class_name}"
definition = "{pipe_definition}"
```
Old syntax will be removed in v0.3.0.
                            """)
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

    @classmethod
    def make_pipe_from_details_dict(
        cls,
        domain_code: str,
        pipe_code: str,
        details_dict: Dict[str, Any],
    ) -> PipeAbstract:
        # Delegate to the new make_pipe_from_blueprint method
        return cls.make_pipe_from_blueprint(
            domain_code=domain_code,
            pipe_code=pipe_code,
            details_dict=details_dict,
        )

    @classmethod
    def load_pipe_from_blueprint(
        cls,
        pipe_code: str,
        pipe_blueprint: PipeBlueprint,
    ) -> PipeAbstract:
        """Create a Pipe from a concrete PipeBlueprint instance.

        This resolves the corresponding factory by converting the blueprint class name
        (e.g. "PipeLLMBlueprint") to its factory name ("PipeLLMFactory").
        """
        # The blueprint must be a concrete subclass like PipeLLMBlueprint, PipeOcrBlueprint, etc.
        blueprint_class_name = type(pipe_blueprint).__name__
        if blueprint_class_name == "PipeBlueprint":
            raise PipeFactoryError("Cannot load pipe from base PipeBlueprint. Please provide a specific blueprint subclass (e.g. PipeLLMBlueprint).")

        # Derive factory name: PipeLLMBlueprint -> PipeLLMFactory
        factory_class_name = blueprint_class_name.replace("Blueprint", "Factory")

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

        # Domain is part of the blueprint
        domain_code = pipe_blueprint.domain

        # Let the specific factory build the concrete Pipe instance
        pipe_from_blueprint: PipeAbstract = pipe_factory.make_pipe_from_blueprint(
            domain_code=domain_code,
            pipe_code=pipe_code,
            pipe_blueprint=pipe_blueprint,  # type: ignore[arg-type]
        )
        return pipe_from_blueprint

    @classmethod
    def make_pipe_blueprint_from_details(
        cls,
        domain_code: str,
        details_dict: Dict[str, Any],
    ) -> PipeBlueprint:
        """Create a concrete PipeBlueprint subclass instance from details.

        This resolves the factory based on the provided details (supports both
        new and legacy formats), locates the corresponding <PipeClassName>Blueprint
        in the factory module, and validates the blueprint.
        """
        # Determine pipe class name from details
        if "type" in details_dict and "definition" in details_dict:
            pipe_class_name = details_dict["type"]
            normalized_details = details_dict.copy()
        else:
            try:
                pipe_class_name, legacy_definition = next(iter(details_dict.items()))
                normalized_details = {"definition": legacy_definition}
            except StopIteration as empty_err:
                raise PipeFactoryError("Pipe details are empty; cannot determine pipe type") from empty_err

        factory_class_name = f"{pipe_class_name}Factory"

        # Resolve factory to locate its module (where the Blueprint class is defined)
        try:
            pipe_factory: Type[PipeSpecificFactoryProtocol[Any, Any]] = KajsonManager.get_class_registry().get_required_subclass(
                name=factory_class_name,
                base_class=PipeSpecificFactoryProtocol,
            )
        except ClassRegistryNotFoundError as factory_not_found_error:
            raise PipeFactoryError(
                f"Factory '{factory_class_name}' not found for pipe type '{pipe_class_name}': {factory_not_found_error}"
            ) from factory_not_found_error
        except ClassRegistryInheritanceError as factory_inheritance_error:
            raise PipeFactoryError(
                f"Factory '{factory_class_name}' is not a subclass of {type(PipeSpecificFactoryProtocol)}."
            ) from factory_inheritance_error

        factory_module = importlib.import_module(pipe_factory.__module__)
        blueprint_class_name = f"{pipe_class_name}Blueprint"

        try:
            blueprint_cls: Type[PipeBlueprint] = getattr(factory_module, blueprint_class_name)
        except AttributeError as exc:
            raise PipeFactoryError(f"Cannot find blueprint class '{blueprint_class_name}' in module '{pipe_factory.__module__}'") from exc

        details_with_domain = normalized_details.copy()
        details_with_domain["domain"] = domain_code

        return blueprint_cls.model_validate(details_with_domain)
