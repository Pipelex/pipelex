import os
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Type

from typing_extensions import override

from pipelex import log
from pipelex.cogt.inference_backend.model_spec import InferenceModelSpec
from pipelex.cogt.llm.llm_models.llm_deck import LLMDeck, LLMDeckBlueprint
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


class LLMDeckNotFoundError(Exception):
    pass


class DeckManager:
    @property
    def llm_deck_dir_path(self) -> str:
        return ".pipelex/inference/deck"

    def get_llm_deck_paths(self) -> List[str]:
        llm_deck_paths = [str(path) for path in find_files_in_dir(dir_path=self.llm_deck_dir_path, pattern="*.toml", is_recursive=True)]
        llm_deck_paths.sort()
        return llm_deck_paths

    def _validate_toml_files(self):
        log.debug("LibraryManager validating PLX file formatting")

        # Validation of LLM deck paths
        llm_deck_paths = self.get_llm_deck_paths()
        for llm_deck_path in llm_deck_paths:
            if os.path.exists(llm_deck_path):
                try:
                    validate_toml_file(llm_deck_path)
                except TOMLValidationError as exc:
                    log.error(f"PLX formatting issues in LLM deck file '{llm_deck_path}': {exc}")
                    raise LibraryError(f"PLX validation failed for LLM deck file '{llm_deck_path}': {exc}") from exc

    def load_deck(self) -> LLMDeck:
        llm_deck_paths = self.get_llm_deck_paths()
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

        llm_deck = LLMDeck.model_validate(full_llm_deck_dict)
        return llm_deck
