"""Combined model/backend fixtures for efficient parametrized testing.

This module provides fixtures that combine model selection with backend routing,
using pre-computed valid (model, backend) pairs from the generated fixtures file.
This eliminates the need for collection-time filtering and reduces test collection
overhead significantly.

Usage:
    @pytest.mark.llm
    @pytest.mark.inference
    @pytest.mark.asyncio(loop_scope="class")
    class TestExample:
        async def test_something(self, llm_combo: ModelCombo):
            # Test with this specific model/backend combination
            llm_handle = llm_combo.handle
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from pipelex.hub import get_console
from pipelex.pipelex import Pipelex
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit, save_toml_to_path
from tests.integration.pipelex.fixtures.model_selection import (
    ModelCombo,
    get_extract_combos,
    get_img_gen_combos,
    get_llm_combos,
    get_search_combos,
)


def _setup_routing_for_backend(backend_name: str) -> tuple[MonkeyPatch, Path]:
    """Set up routing profile override for a specific backend.

    This function:
    1. Tears down any existing Pipelex instance
    2. Sets up the routing monkeypatch BEFORE Pipelex initialization
    3. Reinitializes Pipelex with the correct routing

    Args:
        backend_name: Name of the backend to route to.

    Returns:
        Tuple of (monkeypatch instance, temp directory path) for cleanup.
    """
    # Teardown existing Pipelex (from reset_pipelex_config_fixture)
    Pipelex.teardown_if_needed()

    # Set up routing BEFORE Pipelex.make()
    routing_profile_name = f"all_{backend_name}"
    routing_monkeypatch = MonkeyPatch()
    routing_profiles_path = Path(config_manager.routing_profiles_file_path)
    routing_profiles_doc = load_toml_with_tomlkit(str(routing_profiles_path))
    routing_profiles_doc["active"] = routing_profile_name
    routing_override_dir = Path(tempfile.mkdtemp(prefix="pipelex-routing-override-"))
    routing_override_path = routing_override_dir / routing_profiles_path.name
    save_toml_to_path(routing_profiles_doc, path=str(routing_override_path))
    routing_monkeypatch.setattr(
        type(config_manager),
        "routing_profiles_file_path",
        property(lambda _self: str(routing_override_path)),
    )
    get_console().print(f"[cyan]Routing to backend:[/cyan] {backend_name}")

    # Reinitialize Pipelex with correct routing
    # Use try/except to ensure cleanup on failure
    try:
        integration_mode = IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST
        Pipelex.make(integration_mode=integration_mode)
    except Exception:
        # Clean up on failure to prevent resource leak
        routing_monkeypatch.undo()
        shutil.rmtree(routing_override_dir, ignore_errors=True)
        raise

    return routing_monkeypatch, routing_override_dir


def _cleanup_routing(monkeypatch: MonkeyPatch, temp_dir: Path) -> None:
    """Clean up routing profile override.

    This function:
    1. Tears down Pipelex (which used the monkeypatched routing)
    2. Undoes the monkeypatch
    3. Removes the temp directory

    Args:
        monkeypatch: Monkeypatch instance to undo.
        temp_dir: Temporary directory to remove.
    """
    Pipelex.teardown_if_needed()
    monkeypatch.undo()
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="module", params=get_llm_combos())
def llm_combo(request: pytest.FixtureRequest):
    """Provides a valid ModelCombo(handle, backend) with routing configured.

    This fixture:
    1. Gets a pre-validated combo from the generated fixtures
    2. Sets up the routing profile for the backend
    3. Yields the ModelCombo
    4. Cleans up the routing override

    Yields:
        ModelCombo(handle, backend) for the LLM.
    """
    combo: ModelCombo = request.param
    monkeypatch, temp_dir = _setup_routing_for_backend(combo.backend)

    yield combo

    _cleanup_routing(monkeypatch, temp_dir)


@pytest.fixture(scope="module", params=get_img_gen_combos())
def img_gen_combo(request: pytest.FixtureRequest):
    """Provides a valid ModelCombo(handle, backend) for image generation with routing configured.

    Yields:
        ModelCombo(handle, backend) for image generation.
    """
    combo: ModelCombo = request.param
    monkeypatch, temp_dir = _setup_routing_for_backend(combo.backend)

    yield combo

    _cleanup_routing(monkeypatch, temp_dir)


@pytest.fixture(scope="module", params=get_extract_combos())
def extract_combo(request: pytest.FixtureRequest):
    """Provides a valid ModelCombo(handle, backend) for extraction with routing configured.

    Yields:
        ModelCombo(handle, backend) for extraction.
    """
    combo: ModelCombo = request.param
    monkeypatch, temp_dir = _setup_routing_for_backend(combo.backend)

    yield combo

    _cleanup_routing(monkeypatch, temp_dir)


@pytest.fixture(scope="module", params=get_search_combos())
def search_combo(request: pytest.FixtureRequest):
    """Provides a valid ModelCombo(handle, backend) for search with routing configured.

    Yields:
        ModelCombo(handle, backend) for search.
    """
    combo: ModelCombo = request.param
    monkeypatch, temp_dir = _setup_routing_for_backend(combo.backend)

    yield combo

    _cleanup_routing(monkeypatch, temp_dir)
