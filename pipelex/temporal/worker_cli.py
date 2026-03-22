"""python -m pipelex.temporal.worker_cli
python -m pipelex.temporal.worker_cli --is-unit-testing
python -m pipelex.temporal.worker_cli --is-not-sandboxed
python -m pipelex.temporal.worker_cli --task-queue my_task_queue
"""

import asyncio
import os
from typing import Annotated

import typer

from pipelex import log
from pipelex.config import get_config
from pipelex.pipelex import Pipelex
from pipelex.system.runtime import RunMode, runtime_manager
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.tools.misc.toml_utils import load_toml_from_path

app = typer.Typer()


async def run_worker(
    project: str | None = None,
    is_not_sandboxed: bool = False,
    is_unit_testing: bool = False,
    task_queue: str | None = None,
):
    if project is None:
        log.info(f"Starting worker for current project '{project}', from {os.path.relpath(__file__)}")
    else:
        log.info(f"Starting worker for chosen project '{project}', from {os.path.relpath(__file__)}")
    await get_task_manager().run_worker(is_not_sandboxed=is_not_sandboxed, is_unit_testing=is_unit_testing, task_queue=task_queue)


@app.command()
def configure(
    project: Annotated[str | None, typer.Argument(help="The project name if you don't want to get it from pyproject.toml")] = None,
    is_not_sandboxed: Annotated[bool, typer.Option(help="Flag to run without sandbox")] = False,
    is_unit_testing: Annotated[bool, typer.Option(help="Flag to indicate if running unit tests")] = False,
    task_queue: Annotated[str | None, typer.Option(help="The task queue to use")] = None,
):
    if is_unit_testing:
        runtime_manager.set_run_mode(RunMode.UNIT_TEST)
    if project is None:
        pyproject = load_toml_from_path(path="pyproject.toml")
        project = pyproject.get("project", {}).get("name") or pyproject.get("tool", {}).get("poetry", {}).get("name")
        if not project:
            msg = "Project name not found in pyproject.toml"
            raise ValueError(msg)

    Pipelex.make(temporal_enabled=True)

    # Load base library from PIPELEXPATH at worker startup.
    # This generates dynamic concept classes and registers them with Kajson (fixing deserialization)
    # and populates the pipe library (fixing get_required_pipe() for controllers).
    from pipelex.hub import get_library_manager, resolve_library_dirs, set_current_library  # noqa: PLC0415

    library_manager = get_library_manager()
    library_manager.open_library(library_id="worker_base")
    set_current_library(library_id="worker_base")
    effective_dirs, source_label = resolve_library_dirs(library_dirs=None)
    if effective_dirs:
        log.info(f"Worker loading base library from {len(effective_dirs)} directory(ies) ({source_label})")
        library_manager.load_libraries(library_id="worker_base", library_dirs=effective_dirs)
    else:
        log.info("No library directories configured for worker (PIPELEXPATH not set)")

    if not get_config().temporal.is_enabled:
        log.warning("temporal.is_enabled is false in config, but forcing it on for worker mode")
        updated_temporal = get_config().temporal.model_copy(update={"is_enabled": True})
        get_config().temporal = updated_temporal

    asyncio.run(run_worker(project, is_not_sandboxed, is_unit_testing, task_queue))


if __name__ == "__main__":
    app()
