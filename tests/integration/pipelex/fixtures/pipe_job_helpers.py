import uuid
from collections.abc import Callable, Generator
from pathlib import Path

from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.method_hub import clear_current_library, get_library_manager, get_required_pipe, set_current_library
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.pipeline.pipeline_models import SpecialPipelineId
from pipelex.system.telemetry.otel_constants import OTelConstants

PIPE_JOB_HELPERS_PIPELINE_RUN_ID_PREFIX = "pipe_job_helpers_test"


def build_pipe_job(
    pipe: PipeAbstract,
    library_crate: LibraryCrate | None,
    pipe_run_mode: PipeRunMode = PipeRunMode.DRY,
    pipeline_run_id: str | None = None,
) -> PipeJob:
    """Build a PipeJob with empty working memory and default metadata."""
    resolved_pipeline_run_id = SpecialPipelineId.DRY_RUN_UNTITLED if pipe_run_mode.is_dry else (pipeline_run_id or _make_unique_pipeline_run_id())
    return PipeJobFactory.make_pipe_job(
        pipe=pipe,
        pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        job_metadata=JobMetadata(user_id=OTelConstants.DEFAULT_USER_ID, pipeline_run_id=resolved_pipeline_run_id),
        working_memory=WorkingMemoryFactory.make_empty(),
        library_crate=library_crate,
    )


def _make_unique_pipeline_run_id() -> str:
    return f"{PIPE_JOB_HELPERS_PIPELINE_RUN_ID_PREFIX}_{uuid.uuid4().hex[:8]}"


def pipe_job_from_library(
    load_fn: Callable[[str], None],
    pipe_code: str,
    pipe_run_mode: PipeRunMode = PipeRunMode.DRY,
    isolated_registry: bool = False,
    working_memory_builder: Callable[[PipeAbstract], WorkingMemory] | None = None,
) -> Generator[PipeJob, None, None]:
    """Shared fixture skeleton: open library, load via load_fn, build PipeJob, yield, teardown.

    Args:
        load_fn: Callable that loads content into the library.
        pipe_code: The pipe code to look up after loading.
        pipe_run_mode: Dry, mock, or live execution mode.
        isolated_registry: When True, gives the library a scoped ClassRegistry so dynamic
            concept classes are registered there instead of the global KajsonManager
            registry. This simulates a clean worker process where the global registry
            has no dynamic classes, forcing the deferred hydration path.
        working_memory_builder: Optional builder invoked with the looked-up pipe to
            produce a pre-populated working memory (e.g. mock inputs synthesized from
            ``pipe.needed_inputs()``). When omitted, the job carries an empty working
            memory.
    """
    library_manager = get_library_manager()
    library_id, library = library_manager.open_library()
    if isolated_registry:
        from kajson.class_registry import ClassRegistry  # noqa: PLC0415
        from kajson.kajson_manager import KajsonManager  # noqa: PLC0415

        # Pre-seed from global so core framework classes (PipeSequenceFactory, etc.)
        # are available. Dynamic concept classes added during load_fn() will go to
        # this scoped registry instead of the global, keeping the global clean.
        global_registry = KajsonManager.get_class_registry()
        scoped_registry = ClassRegistry()
        scoped_registry.register_classes_dict(global_registry.get_classes_dict())
        library.set_class_registry(scoped_registry)
    set_current_library(library_id=library_id)

    pipeline_run_id = _make_unique_pipeline_run_id()
    try:
        load_fn(library_id)

        pipe = get_required_pipe(pipe_code=pipe_code)
        library_crate = library_manager.get_crate(library_id=library_id)
        pipe_job = build_pipe_job(pipe=pipe, library_crate=library_crate, pipe_run_mode=pipe_run_mode, pipeline_run_id=pipeline_run_id)
        if working_memory_builder is not None:
            pipe_job = pipe_job.model_copy(update={"working_memory": working_memory_builder(pipe)})

        yield pipe_job
    finally:
        library_manager.teardown(library_id=library_id)
        clear_current_library()


def pipe_job_from_bundle(
    bundle_file: str,
    pipe_code: str,
    pipe_run_mode: PipeRunMode = PipeRunMode.DRY,
    isolated_registry: bool = False,
) -> Generator[PipeJob, None, None]:
    """Build a PipeJob by loading a bundle from an mthds file."""

    def _load(library_id: str) -> None:
        mthds_content = Path(bundle_file).read_text(encoding="utf-8")
        blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=mthds_content)
        get_library_manager().load_from_blueprints(library_id=library_id, blueprints=[blueprint])

    yield from pipe_job_from_library(_load, pipe_code=pipe_code, pipe_run_mode=pipe_run_mode, isolated_registry=isolated_registry)
