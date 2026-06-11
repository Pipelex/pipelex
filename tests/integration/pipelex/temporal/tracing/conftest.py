"""Fixtures for Temporal graph tracing integration tests.

Provides tracing-enabled PipeJob fixtures and a config fixture
that enables event tracing for the test class.
"""

from collections.abc import Generator
from pathlib import Path

import pytest

from pipelex.config import get_config
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.pipe_run.pipe_job import PipeJob
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle
from tests.integration.pipelex.temporal.tracing.test_data import (
    BatchTracingTestData,
    ParallelTracingTestData,
    SequenceTracingTestData,
)

_TRACING_DIR = Path(__file__).parent.resolve()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test under this directory with gha_disabled.

    The hook receives all session-wide items (not just items below this
    conftest), so filter by file path before adding the marker.

    TODO: Tests under tests/integration/pipelex/temporal/tracing/ hang
    reliably in CI under pytest-xdist parallelism (worker timeouts at
    180s on py3.11+). Pass locally and serially. Root cause is concurrent
    PipeBatch/PipeParallel/PipeSequence + WorkflowEnvironment.start_local
    contention under load. Re-enable once the underlying flake is fixed.
    """
    skip_marker = pytest.mark.gha_disabled
    for item in items:
        item_path = Path(str(item.path)).resolve()
        if _TRACING_DIR in item_path.parents:
            item.add_marker(skip_marker)


@pytest.fixture(scope="class")
def tracing_tmp_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Per-class temp directory for NDJSON trace files."""
    return tmp_path_factory.mktemp("traces")


@pytest.fixture(scope="class", autouse=True)
def enable_tracing(tracing_tmp_dir: Path) -> Generator[None, None, None]:
    """Enable tracing config and point traces_dir to the temp directory.

    Restores original config values and cleans up GraphTracerManager on teardown.
    """
    tracing_config = get_config().pipelex.tracing_config
    original_enabled = tracing_config.is_enabled
    ndjson_config = tracing_config.ndjson
    original_dir = ndjson_config.traces_dir if ndjson_config else ""

    tracing_config.is_enabled = True
    if ndjson_config:
        ndjson_config.traces_dir = str(tracing_tmp_dir)

    yield

    tracing_config.is_enabled = original_enabled
    if ndjson_config:
        ndjson_config.traces_dir = original_dir
    GraphTracerManager.clear_instance()


@pytest.fixture(scope="class")
def sequence_tracing_job(is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
    """PipeJob for native_text_sequence (trace_context injected per-execution by execute_and_assemble)."""
    yield from pipe_job_from_bundle(
        bundle_file=SequenceTracingTestData.BUNDLE_FILE,
        pipe_code=SequenceTracingTestData.PIPE_CODE,
        isolated_registry=is_class_registry_isolated,
    )


@pytest.fixture(scope="class")
def parallel_tracing_job(is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
    """PipeJob for temporal_parallel (trace_context injected per-execution by execute_and_assemble)."""
    yield from pipe_job_from_bundle(
        bundle_file=ParallelTracingTestData.BUNDLE_FILE,
        pipe_code=ParallelTracingTestData.PIPE_CODE,
        isolated_registry=is_class_registry_isolated,
    )


@pytest.fixture(scope="class")
def batch_tracing_job(is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
    """PipeJob for temporal_batch (trace_context injected per-execution by execute_and_assemble)."""
    yield from pipe_job_from_bundle(
        bundle_file=BatchTracingTestData.BUNDLE_FILE,
        pipe_code=BatchTracingTestData.PIPE_CODE,
        isolated_registry=is_class_registry_isolated,
    )
