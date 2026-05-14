"""pipelex worker — Start a Temporal worker."""

import asyncio
from typing import Annotated

import typer

from pipelex import log
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import ErrorContext
from pipelex.pipelex import Pipelex


def worker_cmd(
    is_not_sandboxed: Annotated[
        bool,
        typer.Option("--no-sandbox", help="Run workflows without Temporal sandbox restrictions"),
    ] = False,
    is_unit_testing: Annotated[
        bool,
        typer.Option("--unit-testing", help="Run in unit testing mode"),
    ] = False,
    task_queue: Annotated[
        str | None,
        typer.Option("--task-queue", help="Override the task queue name from config"),
    ] = None,
    scope: Annotated[
        str | None,
        typer.Option("--scope", help="Worker scope name from [temporal.worker_scopes.scopes] (defaults to default_scope)"),
    ] = None,
    profile: Annotated[
        str | None,
        typer.Option(
            "--profile",
            help="Worker runtime profile name from [temporal.worker_runtime_profiles.profiles] (defaults to default_profile)",
        ),
    ] = None,
) -> None:
    """Start a Temporal worker.

    This command initializes Pipelex with Temporal enabled and starts
    a worker that listens for workflow and activity tasks.

    Examples:
        pipelex worker
        pipelex worker --no-sandbox
        pipelex worker --task-queue my_queue
        pipelex worker --scope router
        pipelex worker --profile anthropic-tier4 --scope runner-llm --task-queue anthropic_q
    """
    make_pipelex_for_cli(context=ErrorContext.VALIDATION_BEFORE_PIPE_RUN, temporal_enabled=True)

    from pipelex.temporal.temporal_hub import get_task_manager  # noqa: PLC0415

    try:
        log.info("Starting Temporal worker...")
        asyncio.run(
            get_task_manager().run_worker(
                is_not_sandboxed=is_not_sandboxed,
                is_unit_testing=is_unit_testing,
                task_queue=task_queue,
                scope_name=scope,
                profile_name=profile,
            )
        )
    except KeyboardInterrupt:
        log.info("Worker stopped by user")
    except Exception as exc:
        log.error(f"Worker failed: {exc}")
        typer.secho(f"Worker failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    finally:
        Pipelex.teardown_if_needed()
