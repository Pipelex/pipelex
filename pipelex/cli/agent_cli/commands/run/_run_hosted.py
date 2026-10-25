"""`pipelex-agent run … --runner hosted`: run on a runner, the hosted Pipelex API or another, and answer in the run envelope.

The run commands share this module for every step that differs from a local run: where the run executes (the
flags, then `[run] execution`), the flags a hosted run refuses, the run itself through `pipelex.hosted`, the envelope
its result is reported in, and the problem its failure is reported as. Nothing here boots the local runtime.

A refusal decided here, before anything is sent, is a problem like any local failure, in the operator's view, except a
refusal of the method the run would send, a bundle that does not parse or validate or a bundle file or folder with no
pipe to start at: that is the refusal the runner would answer for the same method, and it is reported in the caller's view
(:func:`agent_error_method_refusal`). A failure of the run itself is the problem the runner answered or the client
decided, in the caller's view, since the runner is someone else's runtime, read as the human CLI reads it
(`pipelex.hosted.error_rendering.describe_hosted_error`): pipelex-sdk's errors and the MTHDS client's carry it, by its
declared members alone, with the next step this client tailors for a failure of its own side and for a bare answer of
the hosted edge, and pipelex's own `HostedRunError`s give theirs. A failure no arm names is this process's own and is
reported as a local one is, in the operator's view: a Pipelex error under its own code, any other exception as
`runtime.unexpected`.
"""

from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING, Any, NoReturn, cast

from mthds.protocol.exceptions import PipelineRequestError
from pipelex_sdk.errors import ApiResponseError

from pipelex.base_exceptions import PipelexError
from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_argument_error,
    agent_error,
    agent_error_problem,
    agent_success_formatted,
)
from pipelex.cli.agent_cli.commands.run._output_helpers import build_run_output, format_run_markdown
from pipelex.errors.problem import ProblemView
from pipelex.hosted.client_factory import make_hosted_client
from pipelex.hosted.error_rendering import describe_hosted_error
from pipelex.hosted.exceptions import HostedRunError, HostedRunInterruptedError
from pipelex.hosted.execution import resolve_run_execution
from pipelex.hosted.hosted_run import HostedRunOutcome, HostedRunRequest, RunStartedCallback, run_hosted
from pipelex.hosted.run_config import RunExecution
from pipelex.system.usage_stats.usage_stats_runs import sent_usage_stats_error, usage_stats_error

if TYPE_CHECKING:
    from pipelex_sdk.client import PipelexAPIClient

#: The `--runner` help, shared by the run commands. Typer renders help as Rich markup, which drops an unescaped `[run]`,
#: so the bracket is escaped as `\[`.
RUNNER_OPTION_HELP = r"Where the run executes: 'local' (this machine) or 'hosted' (the hosted Pipelex API). Default: \[run] execution, else local."
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
        agent_argument_error(
            f"--runner {runner} contradicts --{from_flag}: name one place for the run to execute",
            argument="--runner",
            reason=f"contradicts --{from_flag}",
        )
    try:
        execution = resolve_run_execution(requested=requested)
    except PipelexError as exc:
        # A configuration error is the same one a local boot reads, so its problem gives the same next step.
        agent_error(exc.message, cause=exc)
    if base_url is not None and not execution.is_hosted:
        agent_argument_error(
            "--base-url names the hosted API a hosted run calls, and this run executes locally. Add --runner hosted, or drop --base-url.",
            argument="--base-url",
            reason="only applies to a hosted run",
        )
    return execution


def refuse_local_only_flags(*, dry_run: bool, mock_inputs: bool) -> None:
    """Refuse the flags that steer this machine's runtime, which a hosted run never boots."""
    named = [flag for flag, given in (("--dry-run", dry_run), ("--mock-inputs", mock_inputs)) if given]
    if named:
        agent_argument_error(
            f"{' and '.join(named)} only apply to a run on this machine, and this run executes on the hosted API. "
            "Pass --runner local to run it here.",
            argument=" and ".join(named),
            reason="only applies to a run on this machine",
        )


def agent_error_method_refusal(*, error: PipelexError, message: str, execution: RunExecution) -> NoReturn:
    """Report a refusal of the method a run would start, found on this machine before the run, and exit 1.

    A run reads its method before it starts it, wherever it executes: a bundle that does not parse or does not
    validate, or a bundle file or folder with no pipe to start at, is refused then. On this machine's runtime that is a local
    failure, reported in the operator's view with the command's own sentence (`message`). On a runner, the method is
    refused before it is sent, and the refusal is the one the runner would answer its caller for the same method, so it
    is reported as the runner's answer is, in the caller's view (:meth:`PipelexError.to_problem`): its code, its items
    with their locations and fixes, and the caller's next step, with neither the operator's `diagnostics`, which name the
    error's classes, nor the raise site's own message, which only an operator reads. The Markdown keeps the advice the
    error gives as its tip.

    Args:
        error: The refusal: the invalid verdict, or the lack of a pipe to start at in a bundle file or folder.
        message: The command's own sentence, which a local run reports beside the problem.
        execution: Where the run executes.
    """
    if not execution.is_hosted:
        agent_error(message, cause=error)
    problem = error.to_problem(view=ProblemView.CALLER)
    agent_error_problem(problem=problem, cause=error, noted_error=usage_stats_error(error=error))


def agent_error_hosted(*, error: PipelineRequestError | HostedRunError, credential_sent: bool, exit_code: int = 1) -> NoReturn:
    """Report a run on a runner that failed as its problem, and exit with `exit_code`.

    The problem, the sentence beside it and the advice the Markdown prints as its tip are the ones the human CLI prints
    (`pipelex.hosted.error_rendering.describe_hosted_error`), printed as they came, in the active error format, with no
    member of the envelope this CLI wrote before it reported problems. The usage statistics record what the problem
    says, except for a refusal a server answered, which they record by the code and domain its body sent alone, and not
    at all when it sent none, never by the client's reading of its status.
    """
    view = describe_hosted_error(error=error, credential_sent=credential_sent)
    noted_error = sent_usage_stats_error(error=error) if isinstance(error, ApiResponseError) else usage_stats_error(error=error)
    agent_error_problem(problem=view.problem, cause=error, noted_error=noted_error, message=view.message, exit_code=exit_code)


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
    """Run on the hosted API and print the run envelope, or the failure's problem and exit 1.

    Interrupted by Ctrl-C, the problem is the `HostedRunInterruptedError`'s, naming the run the hosted API had
    acknowledged, which keeps going, and the exit status is 130.
    """
    try:
        client = make_hosted_client(base_url=base_url)
    except PipelexError as exc:
        agent_error(exc.message, cause=exc)
    # Whether the run's requests carry a key, which tells a refused key from a missing one; never the key itself.
    credential_sent = bool(client.api_key)
    started_run_ids: list[str] = []

    def _record_start(*, pipeline_run_id: str) -> None:
        started_run_ids.append(pipeline_run_id)

    try:
        outcome = asyncio.run(_start_and_wait(client=client, request=request, on_started=_record_start))
    except (KeyboardInterrupt, asyncio.CancelledError):
        # Ctrl-C stops the wait, not the run: the problem names the run that keeps going.
        interrupted = HostedRunInterruptedError(pipeline_run_id=started_run_ids[-1] if started_run_ids else None)
        agent_error_hosted(error=interrupted, credential_sent=credential_sent, exit_code=_INTERRUPTED_EXIT_CODE)
    except (PipelineRequestError, HostedRunError) as exc:
        agent_error_hosted(error=exc, credential_sent=credential_sent)
    except Exception as exc:  # ruff: ignore[blind-except]
        # Agent CLI command boundary: a failure no arm above names is this process's own, so it is reported as a local
        # run's is, in the operator's view: a Pipelex error under its own code, any other exception, such as a results
        # body that drifted, as `runtime.unexpected`.
        agent_error(str(exc), cause=exc)
    result = build_hosted_run_output(outcome=outcome, with_memory=with_memory)
    agent_success_formatted(result, markdown_renderer=functools.partial(format_run_markdown, with_memory=with_memory), output_format=output_format)
