import os
from typing import Any, Dict, List

from pipelex import log
from pipelex.cogt.model_deck.llm_deck import LLMDeck, LLMDeckBlueprint
from pipelex.exceptions import (
    LibraryError,
)
from pipelex.tools.misc.file_utils import find_files_in_dir
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import TOMLValidationError, load_toml_from_path, validate_toml_file


class LLMDeckNotFoundError(Exception):
    pass


class DeckManager:
    @classmethod
    def llm_deck_dir_path(cls) -> str:
        return ".pipelex/inference/deck"

    @classmethod
    def get_llm_deck_paths(cls) -> List[str]:
        llm_deck_paths = [str(path) for path in find_files_in_dir(dir_path=cls.llm_deck_dir_path(), pattern="*.toml", is_recursive=True)]
        llm_deck_paths.sort()
        return llm_deck_paths

    @classmethod
    def _validate_toml_files(cls):
        log.debug("LibraryManager deck TOML file formatting")

        # Validation of LLM deck paths
        llm_deck_paths = cls.get_llm_deck_paths()
        for llm_deck_path in llm_deck_paths:
            if os.path.exists(llm_deck_path):
                try:
                    validate_toml_file(llm_deck_path)
                except TOMLValidationError as exc:
                    log.error(f"TOML formatting issues in LLM deck file '{llm_deck_path}': {exc}")
                    raise LibraryError(f"TOML validation failed for LLM deck file '{llm_deck_path}': {exc}") from exc

    @classmethod
    def load_deck_blueprint(cls) -> LLMDeckBlueprint:
        llm_deck_paths = cls.get_llm_deck_paths()
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

        llm_deck_blueprint = LLMDeckBlueprint.model_validate(full_llm_deck_dict)
        return llm_deck_blueprint
