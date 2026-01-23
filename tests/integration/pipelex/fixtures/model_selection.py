"""Model selection utilities for test fixtures.

This module provides utilities for loading pre-computed model/backend pairs
from the generated fixture file, with fallback to runtime computation if
the generated file is not available.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from tests.integration.pipelex.fixtures.model_combo import ModelCombo  # noqa: TC001

# Path to generated fixtures file
GENERATED_FIXTURES_PATH = Path(__file__).parent / "_generated_model_sets.py"


def is_generated_fixtures_available() -> bool:
    """Check if the generated fixtures file exists.

    Returns:
        True if the generated file exists, False otherwise.
    """
    return GENERATED_FIXTURES_PATH.exists()


@cache
def get_llm_combos() -> list[ModelCombo]:
    """Get the list of valid (llm_model, backend) combinations.

    First tries to load from the generated fixtures file, then falls back
    to an empty list if not available.

    Returns:
        List of ModelCombo(handle, backend).
    """
    if is_generated_fixtures_available():
        try:
            from tests.integration.pipelex.fixtures._generated_model_sets import (  # noqa: PLC0415
                LLM_COMBOS,  # noqa: PLC2701
            )

            return list(LLM_COMBOS)
        except ImportError:
            pass

    return []


@cache
def get_img_gen_combos() -> list[ModelCombo]:
    """Get the list of valid (img_gen_model, backend) combinations.

    First tries to load from the generated fixtures file, then falls back
    to an empty list if not available.

    Returns:
        List of ModelCombo(handle, backend).
    """
    if is_generated_fixtures_available():
        try:
            from tests.integration.pipelex.fixtures._generated_model_sets import (  # noqa: PLC0415
                IMG_GEN_COMBOS,  # noqa: PLC2701
            )

            return list(IMG_GEN_COMBOS)
        except ImportError:
            pass

    return []


@cache
def get_extract_combos() -> list[ModelCombo]:
    """Get the list of valid (extract_model, backend) combinations.

    First tries to load from the generated fixtures file, then falls back
    to an empty list if not available.

    Returns:
        List of ModelCombo(handle, backend).
    """
    if is_generated_fixtures_available():
        try:
            from tests.integration.pipelex.fixtures._generated_model_sets import (  # noqa: PLC0415
                EXTRACT_COMBOS,  # noqa: PLC2701
            )

            return list(EXTRACT_COMBOS)
        except ImportError:
            pass

    return []
