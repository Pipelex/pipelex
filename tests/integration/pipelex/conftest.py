import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch
from rich.console import Console

from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.config import ConfigPaths
from pipelex.hub import get_model_deck
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.tools.misc.toml_utils import load_toml_from_path, load_toml_with_tomlkit, save_toml_to_path


def _get_all_routing_profiles() -> list[str]:
    """Load all routing profiles that start with 'all_' for parametrized testing."""
    routing_profiles_doc = load_toml_from_path(ConfigPaths.ROUTING_PROFILES_FILE_PATH)
    profiles = routing_profiles_doc.get("profiles", {})
    all_profiles = sorted(profile_name for profile_name in profiles if profile_name.startswith("all_"))
    return all_profiles or ["pipelex_first"]


def _get_backend_from_profile(profile_name: str) -> str | None:
    """Extract the backend name from an 'all_*' profile name."""
    if not profile_name.startswith("all_"):
        return None
    return profile_name[4:]  # Remove 'all_' prefix


def _check_backend_supports_model(backend_name: str, model_handle: str) -> bool:
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


def pytest_collection_modifyitems(items: list[pytest.Item], config: pytest.Config):  # noqa: ARG001
    """Skip test items where routing profile doesn't support the LLM handle (at collection time)."""
    skipped_count = 0
    for item in items:
        # Only process items that have both _routing_profile_setup and llm_handle
        if not hasattr(item, "callspec"):
            continue

        callspec = item.callspec  # type: ignore[attr-defined]
        callspec_params: dict = callspec.params  # type: ignore[attr-defined]

        # Check for the internal _routing_profile_setup parameter (set by our fixture)
        if "_routing_profile_setup" not in callspec_params or "llm_handle" not in callspec_params:
            continue

        routing_profile = callspec_params.get("_routing_profile_setup")  # type: ignore[attr-defined]
        llm_handle = callspec_params.get("llm_handle")  # type: ignore[attr-defined]

        # Type check to ensure we have strings
        if not isinstance(routing_profile, str) or not isinstance(llm_handle, str):
            continue

        # Extract backend name from routing profile
        backend_name = _get_backend_from_profile(routing_profile)
        if not backend_name:
            continue

        # Check if this backend supports this model
        if not _check_backend_supports_model(backend_name, llm_handle):
            # Add skip marker
            item.add_marker(pytest.mark.skip(reason=f"Backend '{backend_name}' does not support LLM handle '{llm_handle}'"))
            skipped_count += 1


def pytest_report_collectionfinish(config: pytest.Config, start_path: Any, items: Any) -> None:
    """Don't print the 'Skipping N tests' message for backend incompatibility."""
    # This suppresses the yellow warning at collection time


def pytest_terminal_summary(terminalreporter: Any, exitstatus: Any, config: pytest.Config) -> None:  # noqa: ARG001
    """Customize the skip summary to hide backend incompatibility skips."""
    # Access the stats
    if "skipped" in terminalreporter.stats:
        # Filter out the silent skips
        visible_skips: list[Any] = []
        silent_skips: list[Any] = []

        for skip_report in terminalreporter.stats["skipped"]:
            reason: str = skip_report.longrepr[2] if hasattr(skip_report, "longrepr") and skip_report.longrepr else ""
            if "does not support LLM handle" in str(reason):
                silent_skips.append(skip_report)
            else:
                visible_skips.append(skip_report)

        # Replace the stats with only visible skips
        if silent_skips:
            terminalreporter.stats["skipped"] = visible_skips
            # Optionally print a single summary line
            terminalreporter.write_line(f"({len(silent_skips)} backend incompatibility skips hidden)", cyan=True)


def pytest_generate_tests(metafunc: pytest.Metafunc):
    """Dynamically parametrize _routing_profile_setup only for modules that need it."""
    # Only parametrize if the test uses routing_profile_override
    if "routing_profile_override" in metafunc.fixturenames:
        # Parametrize _routing_profile_setup (which will be consumed by reset_pipelex_config_fixture)
        if "_routing_profile_setup" in metafunc.fixturenames:
            metafunc.parametrize("_routing_profile_setup", _get_all_routing_profiles(), indirect=True, scope="module")


@pytest.fixture(scope="module")
def _routing_profile_setup(request: pytest.FixtureRequest):  # pyright: ignore[reportUnusedFunction]
    """Override _routing_profile_setup from root conftest to setup routing before Pipelex init.

    This fixture overrides the base _routing_profile_setup to monkeypatch the routing
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
    Console().print(f"[cyan]Overriding routing profile:[/cyan] {routing_profile_name}")

    yield routing_profile_name

    routing_monkeypatch.undo()
    shutil.rmtree(routing_override_dir, ignore_errors=True)


@pytest.fixture(scope="module")
def routing_profile_override(_routing_profile_setup: str | None) -> str | None:
    """Provide the active routing profile name to tests that need it.

    This is a passthrough fixture that receives the value from the setup fixture.
    """
    return _routing_profile_setup


def _is_llm_handle_supported(llm_handle: str) -> bool:
    """Check if an LLM handle is available in the current model deck."""
    model_deck = get_model_deck()
    return model_deck.is_handle_defined(llm_handle)


@pytest.fixture(
    params=[
        # "llm_for_testing_gen_text",
        # "llm_for_testing_gen_object",
        "llm_for_creative_writing",
    ],
)
def llm_preset_id(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(
    params=[
        # "gpt-4o",
        "gpt-4o-mini",
        # "gpt-4-5-preview",
        # "o1",
        # "o1-mini",
        # "o3",
        # "o3-mini",
        # "gpt-5-mini",
        # "gpt-5-nano",
        # "gpt-5-chat",
        # "gpt-5",
        # "mistral-large",
        # "ministral-3b",
        # "ministral-8b",
        # "mistral-medium",
        # "mistral-medium-2508",
        # "bedrock-mistral-large",
        # "bedrock-claude-3-7-sonnet",
        # "bedrock-meta-llama-3-3-70b-instruct",
        # "bedrock-nova-pro",
        # "pipelex/gpt-4o-mini",
        # "pipelex/claude-3.7-sonnet",
        # "pipelex/gemini-2.0-flash-vertex",
        # "pipelex/gemini-2.0-flash",
        # "claude-4.5-sonnet",
        # "claude-4.1-opus",
        # "claude-4.5-haiku",
        # "claude-4.5-sonnet",
        # "grok-3",
        # "grok-3-mini",
        # "gemini-2.5-flash-lite",
        # "gemini-2.5-flash",
        # "gemini-2.5-pro",
        # "openai/gpt-oss-120b",
        # "meta-llama/llama-4-scout-17b-16e-instruct",
        # "meta-llama/llama-4-maverick-17b-128e-instruct",
        # "moonshotai/kimi-k2-instruct-0905",
    ],
)
def llm_handle(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    llm_handle_param = request.param
    if not _is_llm_handle_supported(llm_handle_param):
        pytest.skip(f"LLM handle '{llm_handle_param}' not available on the active routing profile")
    return llm_handle_param


@pytest.fixture(
    params=[
        # "o1",
        # "o3-mini",
        # "gpt-4o",
        # "gpt-4o-mini",
        # "gpt-5-mini",
        # "gpt-5-nano",
        # "gpt-5-chat",
        # "gpt-4-5-preview",
        # "claude-3-haiku",
        # "claude-3.5-sonnet",
        # "claude-3.7-sonnet",
        # "claude-4.1-opus",
        # "pixtral-12b",
        # "pixtral-large",
        # "gemini-2.5-pro",
        # "gemini-2.5-flash",
        # "mistral-small3.1",
        # "mistral-medium",
        # "mistral-medium-2508",
        "gemini-2.5-flash-lite",
        # "gemini-2.5-flash",
        # "gemini-2.5-pro",
        # "qwen3:8b",
    ],
)
def llm_handle_for_vision(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    llm_handle_param = request.param
    if not _is_llm_handle_supported(llm_handle_param):
        pytest.skip(f"LLM handle '{llm_handle_param}' not available on the active routing profile")
    return llm_handle_param


@pytest.fixture(
    params=[
        Plugin(sdk="openai", backend="openai"),
        Plugin(sdk="azure_openai", backend="azure_openai"),
    ],
)
def plugin_for_openai(request: pytest.FixtureRequest) -> Plugin:
    assert isinstance(request.param, Plugin)
    return request.param


@pytest.fixture(
    params=[
        Plugin(sdk="anthropic", backend="anthropic"),
        Plugin(sdk="bedrock_anthropic", backend="bedrock_anthropic"),
    ],
)
def plugin_for_anthropic(request: pytest.FixtureRequest) -> Plugin:
    assert isinstance(request.param, Plugin)
    return request.param


@pytest.fixture(
    params=[
        # None,
        "https://inference.pipelex.com/v1",
    ],
)
def openai_endpoint(request: pytest.FixtureRequest) -> str | None:
    assert isinstance(request.param, str) or request.param is None
    return request.param


@pytest.fixture(
    params=[
        "gpt-5-mini-2025-08-07",
        # "gpt-5-nano-2025-08-07",
        # "gpt-5-chat-2025-08-07",
        # "gpt-5-mini",
        # "gpt-5-nano",
        # "gpt-5-chat-latest",
        # "gpt-5",
        "gpt-4o-mini",
        # "open-mixtral-8x7b",
        # "google/gemini-2.0-flash",
        # "google/gemini-2.5-pro-preview-05-06",
        # "google/gemini-2.5-pro-preview-06-05",  # not yet on VertexAI
        # "google/gemini-2.5-flash-preview-04-17",
        # "google/gemini-2.5-flash-preview-05-20",
        # "o1",
        # "o4-mini",
        # "bedrock-mistral-large",
        # "sonar",
        # "claude-3-7-sonnet-20250219",
        # "claude-sonnet-4-20250514",
        # "claude-opus-4-20250514",
        # "claude-opus-4-1-20250805",
        # "us.anthropic.claude-sonnet-4-20250514-v1:0",
        # "us.anthropic.claude-opus-4-20250514-v1:0",
        # "us.anthropic.claude-opus-4-1-20250805-v1:0",
        # "sonar",
        # "sonar-pro",
        # "gemma3:4b",
        # "llama4:scout",
        # "mistral-small3.1:24b",
        # "qwen3:8b",
        # "blackboxai/openai/gpt-4o-mini",
        # "pipelex/openai/gpt-4o-mini",
        # "openai/gpt-4o-mini",
        # "grok-3",
        # "grok-3-mini",
        # "pipelex/gpt-4o-mini",
        # "pipelex/claude-3.7-sonnet",
        # "vertex_ai/gemini-2.0-flash",
    ],
)
def llm_id(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    llm_handle_param = request.param
    if not _is_llm_handle_supported(llm_handle_param):
        pytest.skip(f"LLM handle '{llm_handle_param}' not available on the active routing profile")
    return llm_handle_param


@pytest.fixture(
    params=[
        LLMJobParams(
            temperature=0.5,
            max_tokens=None,
            seed=None,
        ),
    ],
)
def llm_job_params(request: pytest.FixtureRequest) -> LLMJobParams:
    assert isinstance(request.param, LLMJobParams)
    return request.param


@pytest.fixture(
    params=[
        # "flux-pro",
        # "flux-pro/v1.1",
        # "flux-pro/v1.1-ultra",
        "fast-lightning-sdxl",
        # "gpt-image-1",
        # "nano-banana",
        # "best-img-gen",
    ],
)
def img_gen_handle(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(
    params=[
        "pypdfium2-extract-text",
        "mistral-ocr",
    ],
)
def extract_handle(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(
    params=[
        "mistral-ocr",
    ],
)
def extract_handle_from_image(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(
    params=[
        "extract_text_from_visuals",
        "extract_text_from_pdf",
    ],
)
def extract_choice_for_pdf(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


@pytest.fixture(
    params=[
        "extract_text_from_visuals",
    ],
)
def extract_choice_for_image(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param
