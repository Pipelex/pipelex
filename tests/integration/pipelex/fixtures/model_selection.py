"""Model selection utilities for test fixtures.

This module provides utilities for loading pre-computed model/backend pairs
from the generated fixture file.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from tests.integration.pipelex.fixtures.model_combo import ModelCombo  # noqa: TC001

# Path to generated fixtures file
GENERATED_FIXTURES_PATH = Path(__file__).parent / "_generated_model_sets.py"

MISSING_FIXTURES_ERROR_MSG = (
    f"Generated test fixtures file not found at {GENERATED_FIXTURES_PATH}.\n"
    "This file is required for model-based tests to run.\n"
    "Please run 'make regenerate-test-models' or 'make install' to generate it."
)


def _ensure_generated_fixtures_exist() -> None:
    """Ensure the generated fixtures file exists, raising an error if not.

    Raises:
        FileNotFoundError: If the generated fixtures file does not exist.
    """
    if not GENERATED_FIXTURES_PATH.exists():
        raise FileNotFoundError(MISSING_FIXTURES_ERROR_MSG)


@cache
def get_llm_combos() -> list[ModelCombo]:
    """Get the list of valid (llm_model, backend) combinations.

    Returns:
        List of ModelCombo(handle, backend).

    Raises:
        FileNotFoundError: If the generated fixtures file does not exist.
    """
    _ensure_generated_fixtures_exist()
    from tests.integration.pipelex.fixtures._generated_model_sets import (  # noqa: PLC0415
        LLM_COMBOS,  # noqa: PLC2701
    )

    return list(LLM_COMBOS)


@cache
def get_img_gen_combos() -> list[ModelCombo]:
    """Get the list of valid (img_gen_model, backend) combinations.

    Returns:
        List of ModelCombo(handle, backend).

    Raises:
        FileNotFoundError: If the generated fixtures file does not exist.
    """
    _ensure_generated_fixtures_exist()
    from tests.integration.pipelex.fixtures._generated_model_sets import (  # noqa: PLC0415
        IMG_GEN_COMBOS,  # noqa: PLC2701
    )

    return list(IMG_GEN_COMBOS)


@cache
def get_extract_combos() -> list[ModelCombo]:
    """Get the list of valid (extract_model, backend) combinations.

    Returns:
        List of ModelCombo(handle, backend).

    Raises:
        FileNotFoundError: If the generated fixtures file does not exist.
    """
    _ensure_generated_fixtures_exist()
    from tests.integration.pipelex.fixtures._generated_model_sets import (  # noqa: PLC0415
        EXTRACT_COMBOS,  # noqa: PLC2701
    )

    return list(EXTRACT_COMBOS)
