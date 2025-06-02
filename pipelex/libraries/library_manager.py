from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Type

from kajson.class_registry import class_registry
from kajson.exceptions import ClassRegistryInheritanceError, ClassRegistryNotFoundError
from pydantic import ValidationError

from pipelex import log
from pipelex.cogt.llm.llm_models.llm_deck import LLMDeck
from pipelex.core.concept_factory import ConceptFactory
from pipelex.core.concept_library import ConceptLibrary
from pipelex.core.concept_native import NativeConcept
from pipelex.core.domain import Domain
from pipelex.core.domain_library import DomainLibrary
from pipelex.core.pipe_abstract import PipeAbstract
from pipelex.core.pipe_blueprint import PipeSpecificFactoryProtocol
from pipelex.core.pipe_library import PipeLibrary
from pipelex.exceptions import ConceptLibraryError, LibraryError, LibraryParsingError, PipeFactoryError, PipeLibraryError
from pipelex.libraries.library_config import LibraryConfig
from pipelex.tools.misc.file_utils import find_files_in_dir
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.tools.runtime_manager import runtime_manager
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error
from pipelex.types import StrEnum


class LibraryComponent(StrEnum):
    CONCEPT = "concept"
    PIPE = "pipe"


class LibraryManager:
    allowed_root_attributes: ClassVar[List[str]] = [
        "domain",
        "definition",
        "system_prompt",
        "system_prompt_to_structure",
        "prompt_template_to_structure",
    ]

    def __init__(self) -> None:
        # TODO : avoid having an Option LLMDeck: regroup with model provider
        self.llm_deck: Optional[LLMDeck] = None
        self.domain_library = DomainLibrary()
        self.concept_library = ConceptLibrary()
        self.pipe_library = PipeLibrary()

    def teardown(self) -> None:
        self.llm_deck = None
        self.pipe_library.teardown()
        self.concept_library.teardown()
        self.domain_library.teardown()

    def load_libraries(self):
        log.debug("LibraryManager loading separate libraries")

        class_registry.register_classes_in_folder(
            folder_path=LibraryConfig.loaded_pipelines_path,
        )
        library_paths = [LibraryConfig.loaded_pipelines_path]
        if runtime_manager.is_unit_testing:
            log.debug("Registering test pipeline structures for unit testing")
            class_registry.register_classes_in_folder(
                folder_path=LibraryConfig.test_pipelines_path,
            )
            library_paths += [LibraryConfig.test_pipelines_path]

        native_concepts = NativeConcept.all_concepts()
        self.concept_library.add_concepts(concepts=native_concepts)

        self._load_combo_libraries(library_paths=library_paths)

    def load_deck(self) -> LLMDeck:
        llm_deck_paths = LibraryConfig.get_llm_deck_paths()
        full_llm_deck_dict: Dict[str, Any] = {}

        for llm_deck_path in llm_deck_paths:
            llm_deck_dict = load_toml_from_path(path=llm_deck_path)
            log.debug(f"Loaded LLM deck from {llm_deck_path}")
            log.verbose(llm_deck_dict)
            deep_update(full_llm_deck_dict, llm_deck_dict)

        self.llm_deck = LLMDeck.model_validate(full_llm_deck_dict)
        return self.llm_deck

    def _load_combo_libraries(self, library_paths: List[str]):
        log.debug("LibraryManager loading combo libraries")
        # Find all .toml files in the directories and their subdirectories
        toml_file_paths: List[Path] = []

        for libraries_path in library_paths:
            # Use the existing utility function specifically for TOML files
            found_file_paths = find_files_in_dir(
                dir_path=libraries_path,
                pattern="*.toml",
                is_recursive=True,
            )
            if not found_file_paths:
                log.warning(f"No TOML files found in library path: {libraries_path}")
            toml_file_paths.extend(found_file_paths)

        # First pass: load all domains
        for toml_path in toml_file_paths:
            library_dict = load_toml_from_path(path=str(toml_path))
            library_name = toml_path.stem
            domain_code = library_dict.get("domain")
            if domain_code is None:
                raise LibraryParsingError(f"Library '{library_name}' has no domain set")
            domain_definition = library_dict.get("definition")
            if domain_definition is None:
                # we skip the domain without definition, it must be defined one and only one time in the domain library
                continue
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
            self.domain_library.add_new_domain(domain=domain)

        # Second pass: load all concepts
        for toml_path in toml_file_paths:
            nb_concepts_before = len(self.concept_library.root)
            library_dict = load_toml_from_path(path=str(toml_path))
            library_name = toml_path.stem
            try:
                self._load_library_dict(library_name=library_name, library_dict=library_dict, component_type=LibraryComponent.CONCEPT)
            except LibraryParsingError as exc:
                raise LibraryError(f"Error parsing library '{library_name}' at '{toml_path}': {exc}") from exc
            nb_concepts_loaded = len(self.concept_library.root) - nb_concepts_before
            log.verbose(f"Loaded {nb_concepts_loaded} concepts from '{toml_path.name}'")

        # Third pass: load all pipes
        for toml_path in toml_file_paths:
            nb_pipes_before = len(self.pipe_library.root)
            library_dict = load_toml_from_path(path=str(toml_path))
            library_name = toml_path.stem
            self._load_library_dict(library_name=library_name, library_dict=library_dict, component_type=LibraryComponent.PIPE)
            nb_pipes_loaded = len(self.pipe_library.root) - nb_pipes_before
            log.verbose(f"Loaded {nb_pipes_loaded} pipes from '{toml_path.name}'")

    def _load_library_dict(self, library_name: str, library_dict: Dict[str, Any], component_type: str):
        if domain_code := library_dict.pop("domain", None):
            if not self.domain_library.get_domain(domain_code=domain_code):
                raise LibraryParsingError(
                    f"Domain '{domain_code}' is has not been defined in the domain libraryn make sure it has exactlyone definition"
                )
            # domain is set at the root of the library
            self._load_library_components_from_recursive_dict(domain_code=domain_code, recursive_dict=library_dict, component_type=component_type)
        else:
            raise LibraryParsingError(f"Library '{library_name}' has no domain set")

    def _load_library_components_from_recursive_dict(self, domain_code: str, recursive_dict: Dict[str, Any], component_type: str):
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
                try:
                    if key == LibraryComponent.CONCEPT:
                        self._load_concepts(domain_code=domain_code, obj_dict=obj_dict)
                    elif key == LibraryComponent.PIPE:
                        self._load_pipes(domain_code=domain_code, obj_dict=obj_dict)
                    else:
                        continue
                except ValidationError as exc:
                    error_msg = format_pydantic_validation_error(exc)
                    error_class = ConceptLibraryError if component_type == LibraryComponent.CONCEPT else PipeLibraryError
                    raise error_class(f"Error loading a {component_type} from domain '{domain_code}' because of: {error_msg}") from exc
            elif key not in [LibraryComponent.CONCEPT, LibraryComponent.PIPE]:
                # Not a concept but a subdomain
                self._load_library_components_from_recursive_dict(domain_code=domain_code, recursive_dict=obj_dict, component_type=component_type)
            else:
                # Skip keys that don't match our criteria
                continue

    def _load_concepts(self, domain_code: str, obj_dict: Dict[str, Any]):
        for concept_code, concept_obj in obj_dict.items():
            if isinstance(concept_obj, str):
                # we only have a definition
                concept_from_def = ConceptFactory.make_concept_from_definition(domain_code=domain_code, code=concept_code, definition=concept_obj)
                self.concept_library.add_new_concept(concept=concept_from_def)
            elif isinstance(concept_obj, dict):
                # blueprint dict definition
                concept_obj_dict: Dict[str, Any] = concept_obj
                concept_from_dict = ConceptFactory.make_from_details_dict(domain_code=domain_code, code=concept_code, details_dict=concept_obj_dict)
                self.concept_library.add_new_concept(concept=concept_from_dict)
            else:
                raise ConceptLibraryError(f"Unexpected type for concept_code '{concept_code}' in domain '{domain_code}': {type(concept_obj)}")

    def _load_pipes(self, domain_code: str, obj_dict: Dict[str, Any]):
        for pipe_code, pipe_obj in obj_dict.items():
            if isinstance(pipe_obj, str):
                # TODO: handle one-liner
                pass
            elif isinstance(pipe_obj, dict):
                pipe_obj_dict: Dict[str, Any] = pipe_obj.copy()
                pipe = LibraryManager.make_pipe_from_details_dict(
                    domain_code=domain_code,
                    pipe_code=pipe_code,
                    details_dict=pipe_obj_dict,
                )
                self.pipe_library.add_new_pipe(pipe=pipe)

    def validate_libraries(self):
        log.debug("LibraryManager validating libraries")
        if self.llm_deck is None:
            raise LibraryError("LLM deck is not loaded")
        LLMDeck.final_validate(deck=self.llm_deck)
        self.concept_library.validate_with_libraries()
        self.pipe_library.validate_with_libraries()
        self.domain_library.validate_with_libraries()

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
            pipe_factory: Type[PipeSpecificFactoryProtocol[Any, Any]] = class_registry.get_required_subclass(
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
