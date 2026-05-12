from collections.abc import Callable, Generator
from pathlib import Path

import pytest

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.hub import get_library_manager, get_required_pipe
from pipelex.pipe_run.dry_run import convert_to_working_memory_format
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.fixtures.pipe_job_helpers import build_pipe_job, pipe_job_from_bundle, pipe_job_from_library
from tests.integration.pipelex.temporal.test_data import (
    CombinedPipelineTemporalTestData,
    ConflictConceptAlphaTestData,
    ConflictConceptBetaTestData,
    ConflictPipeAlphaTestData,
    ConflictPipeBetaTestData,
    CvBatchScreeningTemporalTestData,
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


# --- CV batch screening fixture (deeply-nested controller + PipeExtract + PipeLLM) ---


@pytest.fixture(scope="class")
def cv_batch_screening_job(pipe_run_mode: PipeRunMode, is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
    """PipeJob for the CV batch screening pipeline, pre-populated with mock cvs + job_offer_pdf.

    Mirrors the demos example 21 pipeline (PipeSequence -> PipeSequence -> PipeBatch).
    The top-level pipe requires ``cvs: Document[]`` and ``job_offer_pdf: Document``
    inputs; we synthesize them via ``make_mock_inputs`` so the fixture works in dry
    mode (the default for the temporal in-process test).
    """

    def _load(library_id: str) -> None:
        mthds_content = Path(CvBatchScreeningTemporalTestData.BUNDLE_FILE).read_text(encoding="utf-8")
        from pipelex.core.interpreter.interpreter import PipelexInterpreter  # noqa: PLC0415

        blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=mthds_content)
        get_library_manager().load_from_blueprints(library_id=library_id, blueprints=[blueprint])

    yield from _cv_job_iter(_load, pipe_run_mode=pipe_run_mode, isolated_registry=is_class_registry_isolated)


def _cv_job_iter(
    load_fn: Callable[[str], None],
    pipe_run_mode: PipeRunMode,
    isolated_registry: bool,
) -> Generator[PipeJob, None, None]:
    """Shared library-open/build/teardown sequence for the CV batch screening fixture.

    Captures ``library_id`` as a local so we can fetch the crate without depending on
    a ``get_current_library_id`` accessor on the manager protocol.
    """
    from pipelex.hub import set_current_library, teardown_current_library  # noqa: PLC0415

    library_manager = get_library_manager()
    library_id, library = library_manager.open_library()
    if isolated_registry:
        from kajson.class_registry import ClassRegistry  # noqa: PLC0415
        from kajson.kajson_manager import KajsonManager  # noqa: PLC0415

        global_registry = KajsonManager.get_class_registry()
        scoped_registry = ClassRegistry()
        scoped_registry.register_classes_dict(global_registry.get_classes_dict())
        library.set_class_registry(scoped_registry)
    set_current_library(library_id=library_id)

    try:
        load_fn(library_id)
        pipe = get_required_pipe(pipe_code=CvBatchScreeningTemporalTestData.PIPE_CODE)
        needed_inputs = convert_to_working_memory_format(needed_inputs_spec=pipe.needed_inputs())
        working_memory = WorkingMemoryFactory.make_mock_inputs(needed_inputs=needed_inputs)
        library_crate = library_manager.get_crate(library_id=library_id)
        job = build_pipe_job(pipe=pipe, library_crate=library_crate, pipe_run_mode=pipe_run_mode)
        yield job.model_copy(update={"working_memory": working_memory})
    finally:
        library_manager.teardown(library_id=library_id)
        teardown_current_library()
