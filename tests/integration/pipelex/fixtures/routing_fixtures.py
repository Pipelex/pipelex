"""Routing profile fixtures and helpers."""

import shutil
import tempfile
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.hub import get_console
from pipelex.system.configuration.configs import ConfigPaths
from pipelex.tools.misc.toml_utils import load_toml_from_path, load_toml_with_tomlkit, save_toml_to_path

# ================================================================================================
# Backend Names for Testing
# Comment out backends you don't want to test
# ================================================================================================

ALL_BACKENDS = [
    # "anthropic",
    # "azure_openai",
    # "bedrock",
    # "blackboxai",
    # "fal",
    # "google",
    # "groq",
    # "mistral",
    # "ollama",
    # "openai",
    PipelexBackend.GATEWAY,
    PipelexBackend.LEGACY_INFERENCE,
    # "vertexai",
    # "xai",
]


def get_all_routing_profiles() -> list[str]:
    """Load all routing profiles that start with 'all_' for parametrized testing."""
    routing_profiles_doc = load_toml_from_path(ConfigPaths.ROUTING_PROFILES_FILE_PATH)
    profiles = routing_profiles_doc.get("profiles", {})

    # Get all profiles starting with 'all_'
    all_profiles = [profile_name for profile_name in profiles if profile_name.startswith("all_")]

    # Filter to only include profiles for enabled backends
    enabled_profiles: list[str] = []
    for profile_name in all_profiles:
        backend_name = extract_backend_from_profile_name_if_possible(profile_name)
        if backend_name and backend_name in ALL_BACKENDS:
            enabled_profiles.append(profile_name)

    return sorted(enabled_profiles)


def extract_backend_from_profile_name_if_possible(profile_name: str) -> str | None:
    """Extract the backend name from an 'all_*' profile name."""
    if not profile_name.startswith("all_"):
        return None
    return profile_name[4:]  # Remove 'all_' prefix


def check_backend_supports_model(backend_name: str, model_handle: str) -> bool:
    """Check if a backend TOML file defines a specific model (statically, without initializing Pipelex)."""
    backend_file = Path(ConfigPaths.BACKENDS_DIR_PATH) / f"{backend_name}.toml"
    if not backend_file.exists():
        return False

    try:
        backend_config = load_toml_from_path(str(backend_file))
        # Check if the model handle is defined as a top-level key (exclude 'defaults')
        return model_handle in backend_config and model_handle != "defaults"
    except Exception:
        return False


@pytest.fixture(scope="module")
def routing_profile_setup(request: pytest.FixtureRequest):  # pyright: ignore[reportUnusedFunction]
    """Override routing_profile_setup from root conftest to setup routing before Pipelex init.

    This fixture overrides the base routing_profile_setup to monkeypatch the routing
    profiles path BEFORE Pipelex.make() is called.

    Note: This is used by reset_pipelex_config_fixture in the root conftest via fixture dependency.
    It gets parameterized via pytest_generate_tests when needed.
    """
    # If no param, just yield None (use default behavior)
    if not hasattr(request, "param"):
        yield None
        return

    routing_profile_name = request.param
    assert isinstance(routing_profile_name, str)

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
    get_console().print(f"[cyan]Overriding routing profile:[/cyan] {routing_profile_name}")

    yield routing_profile_name

    routing_monkeypatch.undo()
    shutil.rmtree(routing_override_dir, ignore_errors=True)


@pytest.fixture(scope="module")
def routing_profile_override(routing_profile_setup: str | None) -> str | None:
    """Provide the active routing profile name to tests that need it.

    This is a passthrough fixture that receives the value from the setup fixture.
    """
    return routing_profile_setup
