"""`pipelex-agent run … --runner hosted`: run on a runner, the hosted Pipelex API or another, and answer in the run envelope.

The run commands share this module for every step that differs from a local run: where the run executes (the
flags, then `[run] execution`), the flags a hosted run refuses, the run itself through `pipelex.hosted`, the envelope
its result is reported in, and the problem its failure is reported as. Nothing here boots the local runtime.

A refusal decided here, before anything is sent, is a problem like any local failure, in the operator's view. A failure
of the run itself is the problem the runner answered or the client decided, in the caller's view, since the runner is
someone else's runtime: pipelex-sdk's errors and the MTHDS client's carry it, and pipelex's own `HostedRunError`s give
theirs. Only a failure no arm names, which is this process's own, is `runtime.unexpected` in the operator's view.
"""

from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING, Any, NoReturn, cast

from mthds.protocol.exceptions import PipelineRequestError
from mthds.protocol.problem.registry import CoreCode
from pipelex_sdk.errors import ApiResponseError, RunFailedError
from pydantic import ValidationError

from pipelex.base_exceptions import PipelexError, ValidationErrorCategory, ValidationErrorItem
from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_argument_error,
    agent_error,
    agent_error_problem,
    agent_success_formatted,
)
from pipelex.cli.agent_cli.commands.run._output_helpers import build_run_output, format_run_markdown
from pipelex.errors.problem import PipelexProblem, ProblemView, caller_view_of
from pipelex.hosted.client_factory import make_hosted_client
from pipelex.hosted.exceptions import HostedMethodInvalidError, HostedRunError, HostedRunInterruptedError, HostedRunPollingError
from pipelex.hosted.execution import resolve_run_execution
from pipelex.hosted.hosted_run import HostedRunOutcome, HostedRunRequest, RunStartedCallback, run_hosted
from pipelex.hosted.run_config import RunExecution
from pipelex.pipeline.validation_errors import problem_item_of, validation_item_code
from pipelex.system.usage_stats.usage_stats_runs import sent_usage_stats_error, usage_stats_error

if TYPE_CHECKING:
    from mthds.protocol.problem.models import Problem, ProblemItem
    from pipelex_sdk.client import PipelexAPIClient
    from pipelex_sdk.error_models import RunErrorReport
    from pipelex_sdk.validation_models import ValidationErrorItem as SentValidationErrorItem

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


#: The members Pipelex declares beside the standard's, which a problem a runner sent may carry in a shape this version
#: does not read; such a member is left out rather than losing the problem around it.
_PIPELEX_PROBLEM_MEMBERS: tuple[str, ...] = ("request_id", "run_error", "diagnostics")


def _holds_diagnostics(*, problem: PipelexProblem) -> bool:
    """Whether a problem, or the run's problem it nests, carries the diagnostics only an operator reads."""
    if problem.diagnostics is not None:
        return True
    return problem.run_error is not None and _holds_diagnostics(problem=problem.run_error)


def received_problem(*, problem: Problem, request_id: str | None = None) -> PipelexProblem:
    """A problem a runner answered or a client decided, as this CLI reports it: as it came, in the caller's view.

    A runner answers its caller in the caller's view already, so the problem is kept member for member, the runner's own
    next step included. One that carries diagnostics, which a runner answers only to its operator, is projected onto the
    caller's view (:func:`caller_view_of`), since this machine is not the runner's operator.

    Args:
        problem: The problem as the standard's client reads it.
        request_id: The request the answer belongs to, when the client read it off the answer and the problem names none.

    Returns:
        The problem, in the caller's view.
    """
    members = problem.as_wire()
    try:
        received = PipelexProblem.model_validate(members)
    except ValidationError:
        for member in _PIPELEX_PROBLEM_MEMBERS:
            members.pop(member, None)
        received = PipelexProblem.model_validate(members)
    if request_id and received.request_id is None:
        received = received.with_members(request_id=request_id)
    return caller_view_of(problem=received) if _holds_diagnostics(problem=received) else received


def _stored_run_problem(*, report: RunErrorReport | None) -> PipelexProblem | None:
    """The failed run's own problem, when the report the hosted API stored for it is a problem document; ``None`` otherwise."""
    if report is None:
        return None
    try:
        stored = PipelexProblem.model_validate(report.model_dump(mode="json", exclude_none=True))
    except ValidationError:
        return None
    return caller_view_of(problem=stored)


def _typed_sent_item(*, sent: SentValidationErrorItem) -> ValidationErrorItem:
    """A validation item the hosted API sent, typed as this version reads one.

    An item of a newer runner, of a type or with a member this version does not read, keeps its locators, and its
    sentence becomes the finding of the item no stage classified.
    """
    try:
        return ValidationErrorItem.model_validate(sent.model_dump(mode="json", exclude_none=True))
    except ValidationError:
        return ValidationErrorItem(
            category=ValidationErrorCategory.BLUEPRINT_VALIDATION,
            message=sent.message,
            pipe_code=sent.pipe_code,
            concept_code=sent.concept_code,
            domain_code=sent.domain_code,
            source=sent.source,
            field_path=sent.field_path,
            field_name=sent.field_name,
        )


def hosted_method_problem_items(*, validation_errors: list[SentValidationErrorItem]) -> list[ProblemItem]:
    """The problem items of the hosted API's verdict that a method does not load, as a local verdict codes its items.

    Each item takes the code its type gives it, and ``method.schema_violation``, whose sentence quotes the item's own
    finding, when it has no type this version reads. Each item's ``source``, the label the file was sent under, is its
    location's ``file``.
    """
    items: list[ProblemItem] = []
    for sent in validation_errors:
        item = _typed_sent_item(sent=sent)
        items.append(problem_item_of(item=item, code=validation_item_code(item=item, residual_code=CoreCode.METHOD_SCHEMA_VIOLATION)))
    return items


def hosted_failure_problem(*, error: PipelineRequestError | HostedRunError) -> PipelexProblem:
    """The problem of a run on a runner that failed, in the caller's view: the runner's, the client's, or pipelex's own.

    - A refusal the runner answered, a runner that cannot be reached and every other failure the client meets carries
      the problem the standard's client decided (`exc.problem`), reported as it came (:func:`received_problem`): the
      runner's own problem document when the answer is one, and otherwise the code the client reads, such as
      `client.unreachable` naming the base URL, or `client.outcome_unknown` for an answer that leaves a run possibly
      started, a server fault on the run request included.
    - A run that started and failed is `run.failed`, naming the run and its status, and nests the run's own problem as
      `run_error` when the report the hosted API stored for it is one.
    - A failure pipelex detects itself is its `HostedRunError`'s problem, naming the run the hosted API acknowledged
      when there is one, and a method the hosted API found does not load lists the hosted API's items as `errors`.

    Args:
        error: The failure.

    Returns:
        The problem, in the caller's view.
    """
    if isinstance(error, HostedMethodInvalidError):
        problem = error.to_problem(view=ProblemView.CALLER)
        items = hosted_method_problem_items(validation_errors=error.validation_errors)
        return problem.with_members(errors=[item.as_wire() for item in items]) if items else problem
    if isinstance(error, HostedRunPollingError | HostedRunInterruptedError):
        return error.to_problem(view=ProblemView.CALLER, pipeline_run_id=error.pipeline_run_id)
    if isinstance(error, HostedRunError):
        return error.to_problem(view=ProblemView.CALLER)
    request_id = error.request_id if isinstance(error, ApiResponseError) else None
    problem = received_problem(problem=error.problem, request_id=request_id)
    if isinstance(error, RunFailedError):
        run_error = _stored_run_problem(report=error.error)
        if run_error is not None:
            problem = problem.with_members(run_error=run_error.to_wire())
    return problem


def agent_error_hosted(*, error: PipelineRequestError | HostedRunError, exit_code: int = 1) -> NoReturn:
    """Report a run on a runner that failed as its problem (:func:`hosted_failure_problem`), and exit with `exit_code`.

    The problem is printed as it came, in the active error format, with no member of the envelope this CLI wrote before
    it reported problems. pipelex's own errors add their sentence as `message`, and a run that failed adds the client's,
    which quotes the run's stored reason; a request error of the client adds none, its problem saying it all. The usage
    statistics record what the problem says, except for a refusal a server answered, which they record by the code and
    domain its body sent alone, and not at all when it sent none, never by the client's reading of its status.
    """
    problem = hosted_failure_problem(error=error)
    message: str | None
    if isinstance(error, PipelexError):
        message = error.message
    elif isinstance(error, RunFailedError):
        message = str(error)
    else:
        message = None
    noted_error = sent_usage_stats_error(error=error) if isinstance(error, ApiResponseError) else usage_stats_error(error=error)
    agent_error_problem(problem=problem, cause=error, noted_error=noted_error, message=message, exit_code=exit_code)


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
    started_run_ids: list[str] = []

    def _record_start(*, pipeline_run_id: str) -> None:
        started_run_ids.append(pipeline_run_id)

    try:
        outcome = asyncio.run(_start_and_wait(client=client, request=request, on_started=_record_start))
    except (KeyboardInterrupt, asyncio.CancelledError):
        # Ctrl-C stops the wait, not the run: the problem names the run that keeps going.
        interrupted = HostedRunInterruptedError(pipeline_run_id=started_run_ids[-1] if started_run_ids else None)
        agent_error_hosted(error=interrupted, exit_code=_INTERRUPTED_EXIT_CODE)
    except (PipelineRequestError, HostedRunError) as exc:
        agent_error_hosted(error=exc)
    except Exception as exc:  # ruff: ignore[blind-except]
        # Agent CLI command boundary: a failure no arm above names, such as a results body that drifted, is this
        # process's own, so it is reported as a local run's is, `runtime.unexpected` in the operator's view.
        agent_error(str(exc), cause=exc)
    result = build_hosted_run_output(outcome=outcome, with_memory=with_memory)
    agent_success_formatted(result, markdown_renderer=functools.partial(format_run_markdown, with_memory=with_memory), output_format=output_format)
