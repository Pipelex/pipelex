"""Model selection utilities for test fixtures.

This module provides utilities for loading pre-computed model/backend pairs
from the generated fixture file, with fallback to runtime computation if
the generated file is not available.
"""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path
from typing import cast

from pipelex.system.configuration.configs import ConfigPaths
from pipelex.tools.misc.toml_utils import load_toml_from_path

# Environment variable for selecting test profile
PIPELEX_TEST_PROFILE_ENV = "PIPELEX_TEST_PROFILE"
DEFAULT_PROFILE = "dev"

# Path to generated fixtures file
GENERATED_FIXTURES_PATH = Path(__file__).parent / "_generated_model_sets.py"

# Path to test profiles config
TEST_PROFILES_PATH = Path(ConfigPaths.DEFAULT_CONFIG_DIR_PATH) / "test_profiles.toml"


def get_test_profile_name() -> str:
    """Get the current test profile name from environment variable.

    Returns:
        The test profile name (defaults to 'dev' if not set).
    """
    return os.environ.get(PIPELEX_TEST_PROFILE_ENV, DEFAULT_PROFILE)


@cache
def load_test_profile() -> dict[str, object]:
    """Load the current test profile configuration.

    Returns:
        Profile configuration dictionary.
    """
    profile_name = get_test_profile_name()

    if not TEST_PROFILES_PATH.exists():
        # Return default "full" profile behavior
        return {"include_all": True}

    try:
        profiles_config = load_toml_from_path(str(TEST_PROFILES_PATH))
        profiles = profiles_config.get("profiles", {})
        if profile_name in profiles:
            profile_data = profiles[profile_name]
            if isinstance(profile_data, dict):
                return cast("dict[str, object]", profile_data)
        # Default to full if profile not found
        return {"include_all": True}
    except Exception:
        return {"include_all": True}


def is_generated_fixtures_available() -> bool:
    """Check if the generated fixtures file exists.

    Returns:
        True if the generated file exists, False otherwise.
    """
    return GENERATED_FIXTURES_PATH.exists()


@cache
def get_llm_model_backend_pairs() -> list[tuple[str, str]]:
    """Get the list of valid (llm_model, backend) pairs.

    First tries to load from the generated fixtures file, then falls back
    to an empty list if not available.

    Returns:
        List of (model_handle, backend_name) tuples.
    """
    if is_generated_fixtures_available():
        try:
            from tests.integration.pipelex.fixtures._generated_model_sets import (  # noqa: PLC0415
                LLM_MODEL_BACKEND_PAIRS,  # noqa: PLC2701
            )

            return list(LLM_MODEL_BACKEND_PAIRS)
        except ImportError:
            pass

    return []


@cache
def get_img_gen_model_backend_pairs() -> list[tuple[str, str]]:
    """Get the list of valid (img_gen_model, backend) pairs.

    First tries to load from the generated fixtures file, then falls back
    to an empty list if not available.

    Returns:
        List of (model_handle, backend_name) tuples.
    """
    if is_generated_fixtures_available():
        try:
            from tests.integration.pipelex.fixtures._generated_model_sets import (  # noqa: PLC0415
                IMG_GEN_MODEL_BACKEND_PAIRS,  # noqa: PLC2701
            )

            return list(IMG_GEN_MODEL_BACKEND_PAIRS)
        except ImportError:
            pass

    return []


@cache
def get_extract_model_backend_pairs() -> list[tuple[str, str]]:
    """Get the list of valid (extract_model, backend) pairs.

    First tries to load from the generated fixtures file, then falls back
    to an empty list if not available.

    Returns:
        List of (model_handle, backend_name) tuples.
    """
    if is_generated_fixtures_available():
        try:
            from tests.integration.pipelex.fixtures._generated_model_sets import (  # noqa: PLC0415
                EXTRACT_MODEL_BACKEND_PAIRS,  # noqa: PLC2701
            )

            return list(EXTRACT_MODEL_BACKEND_PAIRS)
        except ImportError:
            pass

    return []


def get_llm_handles() -> list[str]:
    """Get the list of LLM handles from the current profile.

    Returns:
        List of LLM model handles.
    """
    pairs = get_llm_model_backend_pairs()
    # Return unique handles, preserving order
    seen: set[str] = set()
    handles: list[str] = []
    for model, _ in pairs:
        if model not in seen:
            seen.add(model)
            handles.append(model)
    return handles


def get_img_gen_handles() -> list[str]:
    """Get the list of image generation handles from the current profile.

    Returns:
        List of image generation model handles.
    """
    pairs = get_img_gen_model_backend_pairs()
    # Return unique handles, preserving order
    seen: set[str] = set()
    handles: list[str] = []
    for model, _ in pairs:
        if model not in seen:
            seen.add(model)
            handles.append(model)
    return handles


def get_extract_handles() -> list[str]:
    """Get the list of extract handles from the current profile.

    Returns:
        List of extract model handles.
    """
    pairs = get_extract_model_backend_pairs()
    # Return unique handles, preserving order
    seen: set[str] = set()
    handles: list[str] = []
    for model, _ in pairs:
        if model not in seen:
            seen.add(model)
            handles.append(model)
    return handles
