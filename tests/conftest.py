from collections.abc import Callable, Generator
from pathlib import Path

import pytest
import shortuuid
from pytest_mock import MockerFixture

from pipelex import log
from pipelex.hub import get_library_manager, set_current_library
from pipelex.pipelex import Pipelex
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.system.pipelex_service.remote_config import PipelexPosthogConfig, RemoteConfig
from pipelex.system.pipelex_service.remote_config_fetcher import RemoteConfigFetcher
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.tools.misc.terminal_utils import print_to_stderr

pytest_plugins = [
    "pipelex.test_extras.shared_pytest_plugins",
]

TEST_OUTPUTS_DIR = "temp/test_outputs"

# Session-level cache for remote config (using dict to avoid global statement)
_remote_config_cache: dict[str, RemoteConfig] = {}
_original_fetch_remote_config = RemoteConfigFetcher.fetch_remote_config


def _make_default_remote_config() -> RemoteConfig:
    """Create a default RemoteConfig for environments where fetch fails (e.g., Codex Cloud SSL issues)."""
    return RemoteConfig(
        posthog=PipelexPosthogConfig(
            project_api_key="",
            endpoint="https://app.posthog.com",
            is_geoip_enabled=False,
            is_debug_enabled=False,
        ),
        backend_model_specs={},
    )


def _cached_fetch_remote_config() -> RemoteConfig:
    """Wrapper that caches the remote config for the entire test session."""
    if "config" not in _remote_config_cache:
        # In Codex Cloud, use default config to avoid SSL issues with MITM proxy
        if runtime_manager.is_in_codex_cloud:
            print_to_stderr("Using default remote config for Codex Cloud")
            _remote_config_cache["config"] = _make_default_remote_config()
        else:
            print_to_stderr("Fetching remote config to cache it for the entire test session")
            _remote_config_cache["config"] = _original_fetch_remote_config()
    return _remote_config_cache["config"]


@pytest.fixture(scope="session", autouse=True)
def cache_remote_config_for_session(session_mocker: MockerFixture):
    """Cache remote configuration for the entire test session to avoid repeated fetches."""
    session_mocker.patch.object(RemoteConfigFetcher, "fetch_remote_config", _cached_fetch_remote_config)


def _get_test_integration_mode() -> IntegrationMode:
    """Return the appropriate integration mode for tests.

    Uses CI mode in CI environments (no terms acceptance required),
    PYTEST mode for local development (terms acceptance required).
    """
    if runtime_manager.is_ci_testing:
        return IntegrationMode.CI
    else:
        return IntegrationMode.PYTEST


@pytest.fixture(scope="module")
def routing_profile_setup(request: pytest.FixtureRequest):  # noqa: ARG001  # pyright: ignore[reportUnusedFunction]
    """Hook for downstream conftest to inject routing profile setup before Pipelex init.

    This fixture can be overridden in integration/conftest.py to setup routing overrides.
    Note: Used by reset_pipelex_config_fixture via fixture dependency.
    """
    return


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture(routing_profile_setup: str | None):  # noqa: ARG001
    Pipelex.make(integration_mode=_get_test_integration_mode())
    yield
    Pipelex.teardown_if_needed()


@pytest.fixture(scope="class")
def load_test_library() -> Generator[Callable[[list[Path]], None], None, None]:
    library_id = None

    def _load(library_dirs: list[Path]) -> None:
        nonlocal library_id
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        set_current_library(library_id=library_id)

        library_manager.load_libraries(
            library_id=library_id,
            library_dirs=library_dirs,
        )

        log.verbose(f"Loaded libraries: {[str(p) for p in library_dirs]}")

    yield _load

    if library_id is not None:
        library_manager = get_library_manager()
        library_manager.teardown(library_id=library_id)
        log.verbose(f"Torn down library: {library_id}")


@pytest.fixture(scope="class")
def load_empty_library() -> Generator[Callable[[], str], None, None]:
    library_id = None

    def _load() -> str:
        nonlocal library_id
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        set_current_library(library_id=library_id)

        log.verbose(f"Opened empty library: {library_id}")
        return library_id

    yield _load

    if library_id is not None:
        library_manager = get_library_manager()
        library_manager.teardown(library_id=library_id)
        log.verbose(f"Torn down library: {library_id}")


@pytest.fixture
def job_metadata(request: pytest.FixtureRequest) -> JobMetadata:
    """Provide a JobMetadata instance with test-specific values.

    Uses the test node ID as pipeline_run_id for better traceability in logs.
    """
    test_id: str = request.node.nodeid  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    random_code: str = shortuuid.uuid()[:5]
    pipeline_run_id: str = f"{test_id}-{random_code}"
    return JobMetadata(
        user_id="pytest",
        pipeline_run_id=pipeline_run_id,
    )
