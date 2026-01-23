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
from pipelex.system.configuration.configs import ConfigPaths
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit, save_toml_to_path
from tests.integration.pipelex.fixtures.model_selection import (
    ModelCombo,
    get_extract_combos,
    get_img_gen_combos,
    get_llm_combos,
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
