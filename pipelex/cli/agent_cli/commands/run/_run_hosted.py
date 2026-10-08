"""`pipelex-agent run … --runner hosted`: run on the hosted Pipelex API and answer in the run envelope.

The run commands share this module for every step that differs from a local run: where the run executes (the
flags, then `[run] execution`), the flags a hosted run refuses, the run itself through `pipelex.hosted`, and the
envelope its result or its failure is reported in. Nothing here boots the local runtime.
"""

from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING, Any, NoReturn, cast

from mthds.protocol.exceptions import PipelineRequestError
from pipelex_sdk.errors import ApiResponseError, RunFailedError

from pipelex.base_exceptions import PipelexConfigError, PipelexError
from pipelex.cli.agent_cli.commands.agent_cli_factory import AGENT_INIT_FAILURE_HINT
from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_error,
    agent_error_api_response,
    agent_success_formatted,
)
from pipelex.cli.agent_cli.commands.run._output_helpers import build_run_output, format_run_markdown
from pipelex.hosted.client_factory import make_hosted_client
from pipelex.hosted.error_rendering import describe_hosted_error
from pipelex.hosted.exceptions import HostedRunError, HostedRunInterruptedError
from pipelex.hosted.execution import resolve_run_execution
from pipelex.hosted.hosted_run import HostedRunOutcome, HostedRunRequest, RunStartedCallback, run_hosted
from pipelex.hosted.run_config import RunExecution

if TYPE_CHECKING:
    from pipelex_sdk.client import PipelexAPIClient

#: The `--runner` help, shared by the run commands.
RUNNER_OPTION_HELP = "Where the run executes: 'local' (this machine) or 'hosted' (the hosted Pipelex API). Default: [run] execution, else local."
#: The `--hosted/--local` help, shared by the run commands.
HOSTED_OPTION_HELP = "Run on the hosted Pipelex API (key in PIPELEX_API_KEY) or on this machine; the same choice as --runner."
#: The `--base-url` help, shared by the run commands.
BASE_URL_OPTION_HELP = (
    "Origin of the hosted API a hosted run calls, scheme://host[:port]. Overrides PIPELEX_BASE_URL; default https://api.pipelex.com."
)
#: The exit status of a command interrupted by Ctrl-C, the shell's 128 + SIGINT, which Typer gives one too.
_INTERRUPTED_EXIT_CODE = 130


def resolve_agent_run_execution(*, runner: RunExecution | None, hosted: bool | None, base_url: str | None) -> RunExecution:
    """Where this `pipelex-agent run` executes: `--runner` or `--hosted`/`--local`, else `[run] execution`, else local.

    `--runner` and the flag pair name the same choice, so they must agree when both are given. `--base-url` names the
    hosted API a hosted run calls, so it is refused on a run that executes locally rather than ignored.
    """
    from_flag = RunExecution.from_hosted_flag(hosted=hosted)
    requested = runner or from_flag
    if runner is not None and from_flag is not None and runner is not from_flag:
        agent_error(f"--runner {runner} contradicts --{from_flag}: name one place for the run to execute", error_type="ArgumentError")
    try:
        execution = resolve_run_execution(requested=requested)
    except PipelexConfigError as exc:
        # The same configuration a local boot reads, so the same next step a failed boot gives.
        agent_error(exc.message, error_type=type(exc).__name__, cause=exc, hint=AGENT_INIT_FAILURE_HINT)
    except PipelexError as exc:
        agent_error(exc.message, error_type=type(exc).__name__, cause=exc)
    if base_url is not None and not execution.is_hosted:
        agent_error(
            "--base-url names the hosted API a hosted run calls, and this run executes locally. Add --runner hosted, or drop --base-url.",
            error_type="ArgumentError",
        )
    return execution


def refuse_local_only_flags(*, dry_run: bool, mock_inputs: bool) -> None:
    """Refuse the flags that steer this machine's runtime, which a hosted run never boots."""
    named = [flag for flag, given in (("--dry-run", dry_run), ("--mock-inputs", mock_inputs)) if given]
    if named:
        agent_error(
            f"{' and '.join(named)} only apply to a run on this machine, and this run executes on the hosted API. "
            "Pass --runner local to run it here.",
            error_type="ArgumentError",
        )


def agent_error_hosted(*, error: PipelineRequestError | HostedRunError, exit_code: int = 1) -> NoReturn:
    """Report a hosted run's failure in the agent error envelope, and exit with `exit_code`.

    A refusal the hosted API answered carries its problem document and goes through `agent_error_api_response`, whose
    envelope matches a local failure's. Every other failure is reported as `pipelex.hosted.error_rendering` reads it,
    the view the human CLI prints: its class, its reason, its next step and its domain, the run's `pipeline_run_id`
    once the hosted API acknowledged the run (a run that failed, outlived the wait, was lost on the way or was left
    running by an interruption), and the `validation_errors` of a method that does not load. A run that started and
    failed adds its stored report's status, category, model and provider. When the hosted API gave a `retryable`
    verdict, the envelope carries it, `false` included, so the local table keyed on the runner's class never overrides it.
    """
    if isinstance(error, ApiResponseError):
        agent_error_api_response(error=error)
    view = describe_hosted_error(error=error)
    extra: dict[str, Any] = {"hint": view.next_step}
    if view.error_domain is not None:
        extra["error_domain"] = str(view.error_domain)
    if view.retryable is not None:
        extra["retryable"] = view.retryable
    if view.pipeline_run_id is not None:
        extra["pipeline_run_id"] = view.pipeline_run_id
    if view.validation_errors:
        extra["validation_errors"] = [item.model_dump(mode="json", exclude_none=True) for item in view.validation_errors]
    if isinstance(error, RunFailedError):
        extra["run_status"] = str(error.status)
        report = error.error
        if report is not None:
            reported = {"error_category": report.error_category, "model": report.model, "provider": report.provider}
            extra.update({field_name: value for field_name, value in reported.items() if value})
    agent_error(view.message, error_type=view.error_type, cause=error, exit_code=exit_code, **extra)


def build_hosted_run_output(*, outcome: HostedRunOutcome, with_memory: bool) -> dict[str, Any]:
    """The run envelope of a hosted run, in the shape a local run's has.

    Compact, it is the main output's content. With memory, `main_stuff.json` is that content (the hosted API renders
    no Markdown or HTML, so the Markdown output falls back to it), `working_memory` is the whole working memory, and
    `pipeline_run_id` names the run on the hosted API. Nothing is written to disk.
    """
    results = outcome.results
    content: Any = results.main_stuff
    compact_result: dict[str, Any] = cast("dict[str, Any]", content) if isinstance(content, dict) else {"result": content}
    working_memory_dump: dict[str, Any] = results.working_memory.model_dump(mode="json") if results.working_memory is not None else {}
    extra_metadata: dict[str, Any] = {"pipeline_run_id": results.pipeline_run_id}
    if outcome.uploads:
        extra_metadata["uploads"] = [upload.model_dump(mode="json") for upload in outcome.uploads]
    return build_run_output(
        with_memory=with_memory,
        main_stuff_json={"json": content, "markdown": "", "html": ""},
        working_memory_dump=working_memory_dump,
        compact_result=compact_result,
        extra_metadata=extra_metadata,
    )


async def _start_and_wait(*, client: PipelexAPIClient, request: HostedRunRequest, on_started: RunStartedCallback) -> HostedRunOutcome:
    async with client:
        return await run_hosted(client=client, request=request, on_started=on_started)


def run_hosted_for_agent(*, request: HostedRunRequest, base_url: str | None, with_memory: bool, output_format: CliOutputFormat) -> None:
    """Run on the hosted API and print the run envelope, or the error envelope and exit 1.

    Interrupted by Ctrl-C, the error envelope is a `HostedRunInterruptedError` naming the run the hosted API had
    acknowledged, which keeps going, and the exit status is 130.
    """
    try:
        client = make_hosted_client(base_url=base_url)
    except PipelexError as exc:
        agent_error(exc.message, error_type=type(exc).__name__, cause=exc)
    started_run_ids: list[str] = []

    def _record_start(*, pipeline_run_id: str) -> None:
        started_run_ids.append(pipeline_run_id)

    try:
        outcome = asyncio.run(_start_and_wait(client=client, request=request, on_started=_record_start))
    except (KeyboardInterrupt, asyncio.CancelledError):
        # Ctrl-C stops the wait, not the run: the envelope names the run that keeps going.
        interrupted = HostedRunInterruptedError(pipeline_run_id=started_run_ids[-1] if started_run_ids else None)
        agent_error_hosted(error=interrupted, exit_code=_INTERRUPTED_EXIT_CODE)
    except (PipelineRequestError, HostedRunError) as exc:
        agent_error_hosted(error=exc)
    except Exception as exc:  # ruff: ignore[blind-except]
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
        agent_error(str(exc), error_type=type(exc).__name__, cause=exc)
    result = build_hosted_run_output(outcome=outcome, with_memory=with_memory)
    agent_success_formatted(result, markdown_renderer=functools.partial(format_run_markdown, with_memory=with_memory), output_format=output_format)
