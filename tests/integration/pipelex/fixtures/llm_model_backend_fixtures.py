"""Combined LLM model/backend fixtures for efficient parametrized testing.

This module provides fixtures that combine model selection with backend routing,
using pre-computed valid (model, backend) pairs from the generated fixtures file.
This eliminates the need for collection-time filtering and reduces test collection
overhead significantly.

Usage:
    @pytest.mark.llm
    @pytest.mark.inference
    @pytest.mark.asyncio(loop_scope="class")
    class TestExample:
        async def test_something(self, llm_model_backend: tuple[str, str]):
            model_handle, backend_name = llm_model_backend
            # Test with this specific model/backend combination
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from pipelex.hub import get_console
from pipelex.system.configuration.configs import ConfigPaths
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit, save_toml_to_path
from tests.integration.pipelex.fixtures.model_selection import (
    get_extract_model_backend_pairs,
    get_img_gen_model_backend_pairs,
    get_llm_model_backend_pairs,
)


def _setup_routing_for_backend(backend_name: str) -> tuple[MonkeyPatch, Path]:
    """Set up routing profile override for a specific backend.

    Args:
        backend_name: Name of the backend to route to.

    Returns:
        Tuple of (monkeypatch instance, temp directory path) for cleanup.
    """
    routing_profile_name = f"all_{backend_name}"
    routing_monkeypatch = MonkeyPatch()
    routing_profiles_path = Path(ConfigPaths.ROUTING_PROFILES_FILE_PATH)
    routing_profiles_doc = load_toml_with_tomlkit(str(routing_profiles_path))
    routing_profiles_doc["active"] = routing_profile_name
    routing_override_dir = Path(tempfile.mkdtemp(prefix="pipelex-routing-override-"))
    routing_override_path = routing_override_dir / routing_profiles_path.name
    save_toml_to_path(routing_profiles_doc, str(routing_override_path))
    routing_monkeypatch.setattr(
        ConfigPaths,
        "ROUTING_PROFILES_FILE_PATH",
        str(routing_override_path),
    )
    get_console().print(f"[cyan]Routing to backend:[/cyan] {backend_name}")
    return routing_monkeypatch, routing_override_dir


def _cleanup_routing(monkeypatch: MonkeyPatch, temp_dir: Path) -> None:
    """Clean up routing profile override.

    Args:
        monkeypatch: Monkeypatch instance to undo.
        temp_dir: Temporary directory to remove.
    """
    monkeypatch.undo()
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="module", params=get_llm_model_backend_pairs())
def llm_model_backend(request: pytest.FixtureRequest):
    """Provides a valid (model_handle, backend_name) pair with routing configured.

    This fixture:
    1. Gets a pre-validated (model, backend) pair from the generated fixtures
    2. Sets up the routing profile for the backend
    3. Yields the model handle and backend name
    4. Cleans up the routing override

    Yields:
        Tuple of (model_handle, backend_name)
    """
    model_handle, backend_name = request.param
    monkeypatch, temp_dir = _setup_routing_for_backend(backend_name)

    yield (model_handle, backend_name)

    _cleanup_routing(monkeypatch, temp_dir)


@pytest.fixture(scope="module", params=get_img_gen_model_backend_pairs())
def img_gen_model_backend(request: pytest.FixtureRequest):
    """Provides a valid (model_handle, backend_name) pair for image generation with routing configured.

    Yields:
        Tuple of (model_handle, backend_name)
    """
    model_handle, backend_name = request.param
    monkeypatch, temp_dir = _setup_routing_for_backend(backend_name)

    yield (model_handle, backend_name)

    _cleanup_routing(monkeypatch, temp_dir)


@pytest.fixture(scope="module", params=get_extract_model_backend_pairs())
def extract_model_backend(request: pytest.FixtureRequest):
    """Provides a valid (model_handle, backend_name) pair for extraction with routing configured.

    Yields:
        Tuple of (model_handle, backend_name)
    """
    model_handle, backend_name = request.param
    monkeypatch, temp_dir = _setup_routing_for_backend(backend_name)

    yield (model_handle, backend_name)

    _cleanup_routing(monkeypatch, temp_dir)


# Convenience fixtures for just the model handle (when you don't need the backend name)
@pytest.fixture(scope="module")
def llm_handle_from_model_backend(llm_model_backend: tuple[str, str]) -> str:
    """Get just the LLM model handle from the combined fixture.

    Args:
        llm_model_backend: The combined (model, backend) tuple.

    Returns:
        The model handle string.
    """
    model_handle, _ = llm_model_backend
    return model_handle


@pytest.fixture(scope="module")
def img_gen_handle_from_model_backend(img_gen_model_backend: tuple[str, str]) -> str:
    """Get just the image generation model handle from the combined fixture.

    Args:
        img_gen_model_backend: The combined (model, backend) tuple.

    Returns:
        The model handle string.
    """
    model_handle, _ = img_gen_model_backend
    return model_handle


@pytest.fixture(scope="module")
def extract_handle_from_model_backend(extract_model_backend: tuple[str, str]) -> str:
    """Get just the extract model handle from the combined fixture.

    Args:
        extract_model_backend: The combined (model, backend) tuple.

    Returns:
        The model handle string.
    """
    model_handle, _ = extract_model_backend
    return model_handle
