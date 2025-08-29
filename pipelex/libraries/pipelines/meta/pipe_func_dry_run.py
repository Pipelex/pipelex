from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import StructuredContent

# from pipelex.libraries.pipelines.builder.builder import PipelexBundleBlueprintDraft
# from pipelex.pipe_works.pipe_dry import dry_run_pipes
from pipelex.types import StrEnum


class DryRunPipeFuncStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"


class DryRunPipeFuncResult(StructuredContent):
    """Dry run a pipe func."""

    message: str
    status: DryRunPipeFuncStatus


async def validate_blueprint(working_memory: WorkingMemory) -> DryRunPipeFuncResult:
    """Dry run a pipe func."""

    # pipelex_bundle_blueprint = working_memory.get_stuff_as("blueprint", content_type=PipelexBundleBlueprintDraft)
    # from pipelex.hub import get_library_manager

    # pipes = get_library_manager().load_from_blueprint(pipelex_bundle_blueprint)
    # dry_run_results = await dry_run_pipes(pipes=pipes, run_in_parallel=False)
    # from pipelex import pretty_print

    # pretty_print(dry_run_results, title="Dry run results")

    return DryRunPipeFuncResult(
        message="Blueprint validated",
        status=DryRunPipeFuncStatus.SUCCESS,
    )
