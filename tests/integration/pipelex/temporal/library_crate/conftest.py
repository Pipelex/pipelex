from collections.abc import Generator
from pathlib import Path

import pytest

from pipelex.hub import get_library_manager
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle, pipe_job_from_library
from tests.integration.pipelex.temporal.test_data import (
    CombinedPipelineTemporalTestData,
    ConflictConceptAlphaTestData,
    ConflictConceptBetaTestData,
    ConflictPipeAlphaTestData,
    ConflictPipeBetaTestData,
    LibraryCrateTestData,
    MultiConceptAlphaTestData,
    MultiConceptBetaTestData,
    PipeBatchTemporalTestData,
    PipeComposeTemporalTestData,
    PipeConditionTemporalTestData,
    PipeParallelTemporalTestData,
)

# --- Existing fixtures (Phase 2) ---


@pytest.fixture(scope="class")
def pipe_job_from_library_dirs(is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
    """Build a PipeJob by loading a specific bundle file (simulates PIPELEXPATH-style loading).

    Uses library_file_paths instead of library_dirs to avoid picking up unrelated
    .mthds bundles (conflict/multi test bundles) that share the same directory.
    """

    def _load(library_id: str) -> None:
        get_library_manager().load_libraries(
            library_id=library_id,
            library_file_paths=[Path(LibraryCrateTestData.BUNDLE_FILE)],
        )

    yield from pipe_job_from_library(_load, pipe_code=LibraryCrateTestData.PIPE_CODE, isolated_registry=is_class_registry_isolated)


@pytest.fixture(scope="class")
def pipe_job_from_mthds_content(is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
    """Build a PipeJob by loading the test bundle from mthds_content string."""
    yield from pipe_job_from_bundle(
        bundle_file=LibraryCrateTestData.BUNDLE_FILE,
        pipe_code=LibraryCrateTestData.PIPE_CODE,
        isolated_registry=is_class_registry_isolated,
    )


# --- Conflict concept fixtures (Scenario 1) ---


@pytest.fixture(scope="class")
def alpha_concept_job(pipe_run_mode: PipeRunMode, is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
    """PipeJob with concept Result(score, label)."""
    yield from pipe_job_from_bundle(
        bundle_file=ConflictConceptAlphaTestData.BUNDLE_FILE,
        pipe_code=ConflictConceptAlphaTestData.PIPE_CODE,
        pipe_run_mode=pipe_run_mode,
        isolated_registry=is_class_registry_isolated,
    )


@pytest.fixture(scope="class")
def beta_concept_job(pipe_run_mode: PipeRunMode, is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
    """PipeJob with concept Result(value, confidence, is_valid)."""
    yield from pipe_job_from_bundle(
        bundle_file=ConflictConceptBetaTestData.BUNDLE_FILE,
        pipe_code=ConflictConceptBetaTestData.PIPE_CODE,
        pipe_run_mode=pipe_run_mode,
        isolated_registry=is_class_registry_isolated,
    )


# --- Conflict pipe fixtures (Scenario 2) ---


@pytest.fixture(scope="class")
def alpha_pipe_job(pipe_run_mode: PipeRunMode, is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
    """PipeJob with pipe 'shared_step' about colors."""
    yield from pipe_job_from_bundle(
        bundle_file=ConflictPipeAlphaTestData.BUNDLE_FILE,
        pipe_code=ConflictPipeAlphaTestData.PIPE_CODE,
        pipe_run_mode=pipe_run_mode,
        isolated_registry=is_class_registry_isolated,
    )


@pytest.fixture(scope="class")
def beta_pipe_job(pipe_run_mode: PipeRunMode, is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
    """PipeJob with pipe 'shared_step' about animals."""
    yield from pipe_job_from_bundle(
        bundle_file=ConflictPipeBetaTestData.BUNDLE_FILE,
        pipe_code=ConflictPipeBetaTestData.PIPE_CODE,
        pipe_run_mode=pipe_run_mode,
        isolated_registry=is_class_registry_isolated,
    )


# --- Multi-concept fixtures (Scenario 3) ---


@pytest.fixture(scope="class")
def multi_alpha_job(pipe_run_mode: PipeRunMode, is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
    """PipeJob with Profile(name, age) + Summary(headline, body)."""
    yield from pipe_job_from_bundle(
        bundle_file=MultiConceptAlphaTestData.BUNDLE_FILE,
        pipe_code=MultiConceptAlphaTestData.PIPE_CODE,
        pipe_run_mode=pipe_run_mode,
        isolated_registry=is_class_registry_isolated,
    )


@pytest.fixture(scope="class")
def multi_beta_job(pipe_run_mode: PipeRunMode, is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
    """PipeJob with Profile(title, department, level) + Summary(content)."""
    yield from pipe_job_from_bundle(
        bundle_file=MultiConceptBetaTestData.BUNDLE_FILE,
        pipe_code=MultiConceptBetaTestData.PIPE_CODE,
        pipe_run_mode=pipe_run_mode,
        isolated_registry=is_class_registry_isolated,
    )


# --- Controller type coverage fixtures ---


@pytest.fixture(scope="class")
def condition_job(pipe_run_mode: PipeRunMode, is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
    """PipeJob with PipeCondition inside a PipeSequence."""
    yield from pipe_job_from_bundle(
        bundle_file=PipeConditionTemporalTestData.BUNDLE_FILE,
        pipe_code=PipeConditionTemporalTestData.PIPE_CODE,
        pipe_run_mode=pipe_run_mode,
        isolated_registry=is_class_registry_isolated,
    )


@pytest.fixture(scope="class")
def parallel_job(pipe_run_mode: PipeRunMode, is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
    """PipeJob with PipeParallel inside a PipeSequence."""
    yield from pipe_job_from_bundle(
        bundle_file=PipeParallelTemporalTestData.BUNDLE_FILE,
        pipe_code=PipeParallelTemporalTestData.PIPE_CODE,
        pipe_run_mode=pipe_run_mode,
        isolated_registry=is_class_registry_isolated,
    )


@pytest.fixture(scope="class")
def batch_job(pipe_run_mode: PipeRunMode, is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
    """PipeJob with PipeBatch inside a PipeSequence."""
    yield from pipe_job_from_bundle(
        bundle_file=PipeBatchTemporalTestData.BUNDLE_FILE,
        pipe_code=PipeBatchTemporalTestData.PIPE_CODE,
        pipe_run_mode=pipe_run_mode,
        isolated_registry=is_class_registry_isolated,
    )


@pytest.fixture(scope="class")
def compose_job(pipe_run_mode: PipeRunMode, is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
    """PipeJob with PipeCompose operator and dynamic Report concept."""
    yield from pipe_job_from_bundle(
        bundle_file=PipeComposeTemporalTestData.BUNDLE_FILE,
        pipe_code=PipeComposeTemporalTestData.PIPE_CODE,
        pipe_run_mode=pipe_run_mode,
        isolated_registry=is_class_registry_isolated,
    )


@pytest.fixture(scope="class")
def combined_job(pipe_run_mode: PipeRunMode, is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
    """PipeJob with PipeParallel + PipeCondition in a single PipeSequence."""
    yield from pipe_job_from_bundle(
        bundle_file=CombinedPipelineTemporalTestData.BUNDLE_FILE,
        pipe_code=CombinedPipelineTemporalTestData.PIPE_CODE,
        pipe_run_mode=pipe_run_mode,
        isolated_registry=is_class_registry_isolated,
    )
