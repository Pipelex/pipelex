"""python -m deep_flow.worker_cli
python -m deep_flow.worker_cli deep_flow
python -m deep_flow.worker_cli --is-unit-testing
python -m deep_flow.worker_cli --is-not-sandboxed
python -m deep_flow.worker_cli --task-queue my_task_queue
"""

import asyncio
import os
from typing import Annotated

import typer

from pipelex import log
from pipelex.deep_flow.deep_flow_hub import get_task_manager
from pipelex.system.runtime import RunMode, runtime_manager
from pipelex.tools.misc.string_utils import snake_to_pascal_case
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
    from importlib import import_module  # noqa: PLC0415

    project_name_pascal_case = snake_to_pascal_case(project)
    project_class_name = f"{project_name_pascal_case}System"
    project_module = import_module(f"{project}.system")
    project_class = getattr(project_module, project_class_name)
    project_class.make()

    asyncio.run(run_worker(project, is_not_sandboxed, is_unit_testing, task_queue))


if __name__ == "__main__":
    app()
