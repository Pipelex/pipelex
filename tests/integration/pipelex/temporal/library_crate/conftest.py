from collections.abc import Callable, Generator
from pathlib import Path

import pytest

from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.hub import get_library_manager, get_required_pipe, set_current_library, teardown_current_library
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.pipeline.pipeline_models import SpecialPipelineId
from pipelex.system.telemetry.otel_constants import OTelConstants
from tests.integration.pipelex.temporal.test_data import LibraryCrateTestData


def _build_pipe_job(pipe: PipeAbstract, library_crate: LibraryCrate | None) -> PipeJob:
    """Build a PipeJob in DRY mode with empty working memory."""
    return PipeJobFactory.make_pipe_job(
        pipe=pipe,
        pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
        job_metadata=JobMetadata(user_id=OTelConstants.DEFAULT_USER_ID, pipeline_run_id=SpecialPipelineId.DRY_RUN_UNTITLED),
        working_memory=WorkingMemoryFactory.make_empty(),
        library_crate=library_crate,
    )


def _pipe_job_from_library(load_fn: Callable[[str], None]) -> Generator[PipeJob, None, None]:
    """Shared fixture skeleton: open library, load via load_fn, build PipeJob, yield, teardown."""
    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    set_current_library(library_id=library_id)
    try:
        load_fn(library_id)

        pipe = get_required_pipe(pipe_code=LibraryCrateTestData.PIPE_CODE)
        library_crate = library_manager.get_crate(library_id=library_id)
        pipe_job = _build_pipe_job(pipe=pipe, library_crate=library_crate)

        yield pipe_job
    finally:
        library_manager.teardown(library_id=library_id)
        teardown_current_library()


@pytest.fixture(scope="class")
def pipe_job_from_library_dirs() -> Generator[PipeJob, None, None]:
    """Build a PipeJob by loading the test bundle from a directory (PIPELEXPATH-style)."""

    def _load(library_id: str) -> None:
        get_library_manager().load_libraries(
            library_id=library_id,
            library_dirs=[Path(LibraryCrateTestData.BUNDLE_DIR)],
        )

    yield from _pipe_job_from_library(_load)


@pytest.fixture(scope="class")
def pipe_job_from_mthds_content() -> Generator[PipeJob, None, None]:
    """Build a PipeJob by loading the test bundle from mthds_content string."""

    def _load(library_id: str) -> None:
        mthds_content = Path(LibraryCrateTestData.BUNDLE_FILE).read_text(encoding="utf-8")
        blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=mthds_content)
        get_library_manager().load_from_blueprints(library_id=library_id, blueprints=[blueprint])

    yield from _pipe_job_from_library(_load)
