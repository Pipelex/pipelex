from collections.abc import Callable, Generator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import shortuuid
from pytest_mock import MockerFixture

from pipelex import log
from pipelex.hub import get_library_manager, get_report_delegate, set_current_library
from pipelex.pipelex import Pipelex
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.system.pipelex_service.pipelex_service_config import (
    PipelexServiceConfig,
)
from pipelex.system.pipelex_service.pipelex_service_config import (
    load_pipelex_service_config_if_exists as _original_load_pipelex_service_config,
)
from pipelex.system.pipelex_service.remote_config import RemoteConfig
from pipelex.system.pipelex_service.remote_config_fetcher import RemoteConfigFetcher, RemoteConfigResult
from pipelex.system.pipelex_service.types import RemoteConfigSource
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract

if TYPE_CHECKING:
    from pipelex.system.telemetry.telemetry_manager import TelemetryManager

pytest_plugins = [
    "pipelex.test_extras.shared_pytest_plugins",
]

TEST_OUTPUTS_DIR = "temp/test_outputs"

# Session-level cache for remote config (using dict to avoid global statement)
_remote_config_cache: dict[str, RemoteConfig] = {}
_original_fetch_remote_config = RemoteConfigFetcher.fetch_remote_config


def _cached_fetch_remote_config(require_fresh: bool = False) -> "RemoteConfigResult":  # noqa: ARG001
    """Wrapper that caches the remote config for the entire test session.

    The ``require_fresh`` arg matches the new fetcher signature; ignored here because the
    test-session cache exists precisely so we don't re-hit the network mid-suite.
    """
    if "config" not in _remote_config_cache:
        result = _original_fetch_remote_config()
        _remote_config_cache["config"] = result.config
    return RemoteConfigResult(config=_remote_config_cache["config"], source=RemoteConfigSource.FRESH, cached_at=None)


# Session-level cache for pipelex service config to avoid flaky tests from concurrent file reads
_pipelex_service_config_cache: dict[Path, PipelexServiceConfig | None] = {}


def _cached_load_pipelex_service_config(config_dir: Path) -> PipelexServiceConfig | None:
    """Wrapper that caches the pipelex service config for the entire test session.

    This prevents flaky tests caused by concurrent file reads during parallel pytest-xdist execution.
    The cache key includes the config_dir to handle different config directories.
    """
    if config_dir not in _pipelex_service_config_cache:
        _pipelex_service_config_cache[config_dir] = _original_load_pipelex_service_config(config_dir)
    return _pipelex_service_config_cache[config_dir]


def _fast_telemetry_teardown(self: "TelemetryManager") -> None:
    """Skip expensive OTel/PostHog shutdown during tests (~0.49s per call).

    Preserves exception capture cleanup (restores sys.excepthook) and
    singleton clearing. Skips PostHog client.shutdown() which flushes
    queues and joins threads.

    We still shutdown the TracerProvider to stop the BatchSpanProcessor
    background thread, otherwise it may try to export spans after the
    logging system has been torn down, causing RuntimeError.
    """
    if self._exception_capture:  # pyright: ignore[reportPrivateUsage]
        try:
            self._exception_capture.close()  # pyright: ignore[reportPrivateUsage]
        except Exception as exc:
            log.debug(f"Error closing exception capture: {exc}")
    if self._tracer_provider:  # pyright: ignore[reportPrivateUsage]
        try:
            self._tracer_provider.shutdown()  # pyright: ignore[reportPrivateUsage]
        except Exception:  # noqa: S110
            pass  # Suppress all shutdown errors; logging may already be torn down
    TelemetryManagerAbstract.clear_instance()


@pytest.fixture(scope="session", autouse=True)
def cache_configs_for_session(session_mocker: MockerFixture):
    """Cache configurations and optimize teardown for the entire test session."""
    # Cache remote config to avoid repeated network fetches
    session_mocker.patch.object(RemoteConfigFetcher, "fetch_remote_config", _cached_fetch_remote_config)
    # Cache pipelex service config to avoid flaky tests from concurrent file reads
    session_mocker.patch(
        "pipelex.pipelex.load_pipelex_service_config_if_exists",
        _cached_load_pipelex_service_config,
    )
    # Skip expensive telemetry shutdown (OTel + PostHog flush) during tests
    from pipelex.system.telemetry.telemetry_manager import TelemetryManager  # noqa: PLC0415

    session_mocker.patch.object(TelemetryManager, "teardown", _fast_telemetry_teardown)


def _get_test_integration_mode() -> IntegrationMode:
    """Return the appropriate integration mode for tests.

    Uses CI mode in CI environments (no terms acceptance required),
    PYTEST mode for local development (terms acceptance required).
    """
    if runtime_manager.is_ci_testing:
        return IntegrationMode.CI
    else:
        return IntegrationMode.PYTEST


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture():
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
def job_metadata(request: pytest.FixtureRequest) -> Generator[JobMetadata, None, None]:
    """Provide a JobMetadata instance with test-specific values.

    Uses the test node ID as pipeline_run_id for better traceability in logs.
    Opens a registry for the pipeline run ID before the test and closes it after.
    """
    test_id: str = request.node.nodeid  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    random_code: str = shortuuid.uuid()[:5]
    pipeline_run_id: str = f"{test_id}-{random_code}"

    get_report_delegate().open_registry(pipeline_run_id=pipeline_run_id)

    yield JobMetadata(
        user_id="pytest",
        pipeline_run_id=pipeline_run_id,
    )

    get_report_delegate().close_registry(pipeline_run_id=pipeline_run_id)
