"""Model selection utilities for test fixtures.

This module provides utilities for loading pre-computed model/backend pairs
from the generated fixture file.
"""

from __future__ import annotations

import importlib
from functools import cache
from pathlib import Path
from typing import cast

import pytest

from tests.integration.pipelex.fixtures.model_combo import ModelCombo  # ruff: ignore[typing-only-first-party-import]

# Path to generated fixtures file
GENERATED_FIXTURES_PATH = Path(__file__).parent / "_generated_model_sets.py"

MISSING_FIXTURES_ERROR_MSG = (
    f"Generated test fixtures file not found at {GENERATED_FIXTURES_PATH}.\n"
    "This file is required for model-based tests to run.\n"
    "Please run 'make regenerate-test-models' or 'make install' to generate it."
)

GENERATED_FIXTURES_MODULE = "tests.integration.pipelex.fixtures._generated_model_sets"

STALE_FIXTURES_ERROR_MSG = (
    "Generated test fixtures file at {path} has no '{name}': it predates the model family that set belongs to.\n"
    "Please run 'make regenerate-test-models' or 'make install' to regenerate it."
)


def _or_skip(combos: list[ModelCombo], label: str) -> list[ModelCombo]:
    """Return combos as-is, or a single skip-marked param if the list is empty."""
    if combos:
        return combos
    return [pytest.param(None, marks=pytest.mark.skip(reason=f"No {label} combos in test profile"))]  # type: ignore[list-item]


def _ensure_generated_fixtures_exist() -> None:
    """Ensure the generated fixtures file exists, raising an error if not.

    Raises:
        FileNotFoundError: If the generated fixtures file does not exist.
    """
    if not GENERATED_FIXTURES_PATH.exists():
        raise FileNotFoundError(MISSING_FIXTURES_ERROR_MSG)


def _load_generated_combos(*, name: str) -> list[ModelCombo]:
    """Read one combo set from the generated fixtures file, naming the cure when the file is stale.

    The file is gitignored and only the targets the message names regenerate it, so a checkout that
    gains a model family keeps a file without that family's set. The conftest reads these sets at
    import time, where a bare ImportError interrupts the whole session with nothing pointing at the fix.

    Raises:
        FileNotFoundError: If the generated fixtures file does not exist.
        ImportError: If the generated fixtures file has no set of that name.
    """
    _ensure_generated_fixtures_exist()
    generated_module = importlib.import_module(GENERATED_FIXTURES_MODULE)
    if not hasattr(generated_module, name):
        raise ImportError(STALE_FIXTURES_ERROR_MSG.format(path=GENERATED_FIXTURES_PATH, name=name))
    return list(cast("list[ModelCombo]", getattr(generated_module, name)))


@cache
def get_llm_combos() -> list[ModelCombo]:
    """Get the list of valid (llm_model, backend) combinations.

    Returns:
        List of ModelCombo(handle, backend).

    Raises:
        FileNotFoundError: If the generated fixtures file does not exist.
        ImportError: If the generated fixtures file predates this set.
    """
    return _or_skip(_load_generated_combos(name="LLM_COMBOS"), "LLM")


@cache
def get_img_gen_combos() -> list[ModelCombo]:
    """Get the list of valid (img_gen_model, backend) combinations.

    Returns:
        List of ModelCombo(handle, backend).

    Raises:
        FileNotFoundError: If the generated fixtures file does not exist.
        ImportError: If the generated fixtures file predates this set.
    """
    return _or_skip(_load_generated_combos(name="IMG_GEN_COMBOS"), "image generation")


@cache
def get_extract_combos() -> list[ModelCombo]:
    """Get the list of valid (extract_model, backend) combinations.

    Returns:
        List of ModelCombo(handle, backend).

    Raises:
        FileNotFoundError: If the generated fixtures file does not exist.
        ImportError: If the generated fixtures file predates this set.
    """
    return _or_skip(_load_generated_combos(name="EXTRACT_COMBOS"), "extraction")


@cache
def get_judgment_combos() -> list[ModelCombo]:
    """Get the list of valid (judgment_model, backend) combinations.

    Returns:
        List of ModelCombo(handle, backend).

    Raises:
        FileNotFoundError: If the generated fixtures file does not exist.
        ImportError: If the generated fixtures file predates this set.
    """
    return _or_skip(_load_generated_combos(name="JUDGMENT_COMBOS"), "judgment")


@cache
def get_search_combos() -> list[ModelCombo]:
    """Get the list of valid (search_model, backend) combinations.

    Returns:
        List of ModelCombo(handle, backend).

    Raises:
        FileNotFoundError: If the generated fixtures file does not exist.
        ImportError: If the generated fixtures file predates this set.
    """
    return _or_skip(_load_generated_combos(name="SEARCH_COMBOS"), "search")
