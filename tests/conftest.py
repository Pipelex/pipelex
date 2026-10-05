from collections.abc import Callable, Generator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import shortuuid
from pytest_mock import MockerFixture

from pipelex import log
from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library
from pipelex.pipelex import Pipelex
from pipelex.system.environment import PIPELEX_HOME_ENV_KEY
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract

if TYPE_CHECKING:
    from pipelex.system.telemetry.telemetry_manager import TelemetryManager

pytest_plugins = [
    "pipelex.test_extras.shared_pytest_plugins",
]

TEST_OUTPUTS_DIR = "temp/test_outputs"


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
        except Exception:  # ruff: ignore[try-except-pass]
            pass  # Suppress all shutdown errors; logging may already be torn down
    TelemetryManagerAbstract.clear_instance()


@pytest.fixture(scope="session", autouse=True)
def cache_configs_for_session(session_mocker: MockerFixture):
    """Optimize teardown for the entire test session."""
    # Skip expensive telemetry shutdown (OTel + PostHog flush) during tests
    from pipelex.system.telemetry.telemetry_manager import TelemetryManager  # ruff: ignore[import-outside-top-level]

    session_mocker.patch.object(TelemetryManager, "teardown", _fast_telemetry_teardown)


def _get_test_integration_mode() -> IntegrationMode:
    """Return the appropriate integration mode for tests.

    Uses CI mode in CI environments, PYTEST mode for local development.
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


@pytest.fixture
def no_pipelex_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset `PIPELEX_HOME` for a test that stands in a home directory of its own.

    A test that fakes `Path.home()` or `HOME` is asserting about the default `~/.pipelex`, and a
    `PIPELEX_HOME` exported in the developer's shell would move the home configuration directory
    away from the one it faked. A module of such tests opts in with
    `pytestmark = pytest.mark.usefixtures("no_pipelex_home")`.
    """
    monkeypatch.delenv(PIPELEX_HOME_ENV_KEY, raising=False)


@pytest.fixture(scope="class")
def load_test_library() -> Generator[Callable[[list[Path]], None], None, None]:
    library_id = None
    prev_library_id = None

    def _load(library_dirs: list[Path]) -> None:
        nonlocal library_id, prev_library_id
        library_manager = get_library_manager()
        if library_id is None:
            prev_library_id = get_current_library_id_or_none()
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
        # Restore the binding that existed before _load ran (same pattern as scoped_current_library),
        # so an outer scope's current library survives. prev was captured before open_library minted
        # the new id, so this can never resurrect the torn-down library.
        if prev_library_id is not None:
            set_current_library(library_id=prev_library_id)
        else:
            clear_current_library()
        log.verbose(f"Torn down library: {library_id}")


@pytest.fixture(scope="class")
def load_empty_library() -> Generator[Callable[[], str], None, None]:
    library_id = None
    prev_library_id = None

    def _load() -> str:
        nonlocal library_id, prev_library_id
        library_manager = get_library_manager()
        if library_id is None:
            prev_library_id = get_current_library_id_or_none()
        library_id, _ = library_manager.open_library()
        set_current_library(library_id=library_id)

        log.verbose(f"Opened empty library: {library_id}")
        return library_id

    yield _load

    if library_id is not None:
        library_manager = get_library_manager()
        library_manager.teardown(library_id=library_id)
        # Restore the binding that existed before _load ran (same pattern as scoped_current_library),
        # so an outer scope's current library survives. prev was captured before open_library minted
        # the new id, so this can never resurrect the torn-down library.
        if prev_library_id is not None:
            set_current_library(library_id=prev_library_id)
        else:
            clear_current_library()
        log.verbose(f"Torn down library: {library_id}")


@pytest.fixture
def job_metadata(request: pytest.FixtureRequest) -> JobMetadata:
    """Provide a JobMetadata instance with test-specific values.

    Uses the test node ID as pipeline_run_id for better traceability in logs.
    """
    test_id: str = request.node.nodeid  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    random_code: str = shortuuid.uuid()[:5]
    pipeline_run_id: str = f"{test_id}-{random_code}"

    return JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="pytest", pipeline_run_id=pipeline_run_id))
