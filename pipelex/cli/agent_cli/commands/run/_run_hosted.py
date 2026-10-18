"""`pipelex-agent run … --runner hosted`: run on a runner, the hosted Pipelex API or another, and answer in the run envelope.

The run commands share this module for every step that differs from a local run: where the run executes (the
flags, then `[run] execution`), the flags a hosted run refuses, the run itself through `pipelex.hosted`, the envelope
its result is reported in, and the problem its failure is reported as. Nothing here boots the local runtime.

A refusal decided here, before anything is sent, is a problem like any local failure, in the operator's view, except a
refusal of the method the run would send, a bundle that does not parse or validate or a bundle file or folder with no
pipe to start at: that is the refusal the runner would answer for the same method, and it is reported in the caller's view
(:func:`agent_error_method_refusal`). A failure
of the run itself is the problem the runner answered or the client decided, in the caller's view, since the runner is
someone else's runtime: pipelex-sdk's errors and the MTHDS client's carry it, by its declared members alone, with the
next step the human CLI tailors for a failure of the client's own; an answer in a shape that predates the standard's
reads as the core code its status names, lists its validation items under `method.invalid`, or keeps its reason; and
pipelex's own `HostedRunError`s give theirs. A
failure no arm names is this process's own and is reported as a local one is, in the operator's view: a Pipelex error
under its own code, any other exception as `runtime.unexpected`.
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, NoReturn, cast

from mthds.protocol.exceptions import PipelineRequestError
from mthds.protocol.problem.models import NextStep, Problem, ProblemItem, ProblemLocation, SuggestedFix
from mthds.protocol.problem.registry import CoreCode, RetryVerdict, StepKind
from pipelex_sdk.errors import ApiResponseError, ApiUnreachableError, PipelexRequestError, RunFailedError
from pydantic import BaseModel, ValidationError

from pipelex.base_exceptions import PipelexError, ValidationErrorCategory, ValidationErrorItem
from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_argument_error,
    agent_error,
    agent_error_problem,
    agent_success_formatted,
)
from pipelex.cli.agent_cli.commands.run._output_helpers import build_run_output, format_run_markdown
from pipelex.errors.problem import PipelexProblem, ProblemView, caller_view_of, make_problem
from pipelex.hosted.client_factory import make_hosted_client
from pipelex.hosted.error_rendering import answered_in_former_shape, hosted_refusal_problem, sent_verdict, tailored_next_step
from pipelex.hosted.exceptions import HostedMethodInvalidError, HostedRunError, HostedRunInterruptedError, HostedRunPollingError
from pipelex.hosted.execution import resolve_run_execution
from pipelex.hosted.hosted_run import HostedRunOutcome, HostedRunRequest, RunStartedCallback, run_hosted
from pipelex.hosted.run_config import RunExecution
from pipelex.pipeline.validation_errors import problem_item_of, validation_item_code
from pipelex.system.usage_stats.usage_stats_runs import sent_usage_stats_error, usage_stats_error

if TYPE_CHECKING:
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


#: The parts of a problem, each read against the model that declares its members, so that a member neither the standard
#: nor Pipelex declares is left out at every level. A problem's `params` and a fix's `ops` are the code's and the
#: operation's own and are kept whole; the nested `run_error` and Pipelex's other members are read apart.
PROBLEM_PARTS: dict[type[BaseModel], dict[str, type[BaseModel]]] = {
    PipelexProblem: {"next_step": NextStep, "location": ProblemLocation, "errors": ProblemItem},
    ProblemItem: {"location": ProblemLocation, "suggested_fix": SuggestedFix},
}
#: Pipelex's members beside the standard's, each of which a problem a runner sent may carry in a shape this version does
#: not read: it is read apart and left out alone when it does not read, never losing the problem around it.
_PIPELEX_PROBLEM_MEMBERS: tuple[str, ...] = ("request_id", "run_error", "diagnostics")


def _declared_members(*, members: Mapping[str, Any], shape: type[BaseModel]) -> dict[str, Any]:
    """The members of ``members`` that ``shape`` declares, each part it nests read the same way (:data:`PROBLEM_PARTS`)."""
    declared: dict[str, Any] = {}
    parts = PROBLEM_PARTS.get(shape, {})
    for name in shape.model_fields:
        if name not in members:
            continue
        value = members[name]
        part_shape = parts.get(name)
        if part_shape is not None and isinstance(value, Mapping):
            declared[name] = _declared_members(members=cast("Mapping[str, Any]", value), shape=part_shape)
        elif part_shape is not None and isinstance(value, list):
            declared[name] = [
                _declared_members(members=cast("Mapping[str, Any]", item), shape=part_shape) if isinstance(item, Mapping) else item
                for item in cast("list[Any]", value)
            ]
        else:
            declared[name] = value
    return declared


def _holds_diagnostics(*, members: Mapping[str, Any]) -> bool:
    """Whether a document, or the run's problem it nests, carries diagnostics, whatever their shape: only an operator reads them."""
    if "diagnostics" in members:
        return True
    run_error = members.get("run_error")
    return isinstance(run_error, Mapping) and _holds_diagnostics(members=cast("Mapping[str, Any]", run_error))


def _readable_problem(*, members: Mapping[str, Any]) -> PipelexProblem | None:
    """The problem a document's declared members make, each of Pipelex's members kept only when it reads.

    The standard's members are read first, by their declared members alone; then ``request_id`` is added when it is a
    text, and ``run_error`` when it reads the same way, so a nested problem whose own members do not all read is kept
    without them. ``diagnostics`` is never kept: the problem is reported to a caller, who reads none.

    Returns:
        The problem, or ``None`` when the standard's members do not make one.
    """
    declared = _declared_members(members=members, shape=PipelexProblem)
    extensions = {name: declared.pop(name) for name in _PIPELEX_PROBLEM_MEMBERS if name in declared}
    try:
        readable = PipelexProblem.model_validate(declared)
    except ValidationError:
        return None
    run_error = extensions.get("run_error")
    if isinstance(run_error, Mapping):
        nested = _readable_problem(members=cast("Mapping[str, Any]", run_error))
        if nested is not None:
            readable = readable.model_copy(update={"run_error": nested})
    request_id = extensions.get("request_id")
    if isinstance(request_id, str) and request_id:
        readable = readable.model_copy(update={"request_id": request_id})
    return readable


def received_problem(*, problem: Problem, request_id: str | None = None, stored: bool = False) -> PipelexProblem:
    """A problem a runner answered or a client decided, as this CLI reports it: as it came, in the caller's view.

    A runner answers its caller in the caller's view already, so the problem is kept as it came, the runner's own next
    step included, by the members the standard and Pipelex declare alone (:func:`_readable_problem`): a member no reader
    declares, such as the `error_type`, `error_domain` and `retryable` a runner may still write, is left out at every
    level, and one of Pipelex's members that does not read is left out alone. An answer that carries diagnostics, which
    a runner answers only to its operator, is projected onto the caller's view (:func:`caller_view_of`), decided from
    the document as it came, before any member is left out, since this machine is not the runner's operator; so is a
    stored record of a run, which is the operator's, and so is the run's problem an answer nests (`run_error`), which is
    that record, whatever view the answer around it is in.

    The reading never fails: a problem the standard's client validated always makes one, and the last resort for one
    that would not is `runtime.unexpected`, so the command always prints a problem.

    Args:
        problem: The problem as the standard's client reads it.
        request_id: The request the answer belongs to, when the client read it off the answer and the problem names none.
        stored: The problem is a stored record of a run, in its operator's view.

    Returns:
        The problem, in the caller's view.
    """
    members = problem.as_wire()
    received = _readable_problem(members=members)
    if received is None:
        return make_problem(code=CoreCode.RUNTIME_UNEXPECTED, view=ProblemView.CALLER, request_id=request_id)
    if request_id and received.request_id is None:
        received = received.model_copy(update={"request_id": request_id})
    if stored or _holds_diagnostics(members=members):
        return caller_view_of(problem=received)
    if received.run_error is not None:
        # A runner's caller-view answer may still nest the run's record as it was stored, in its operator's view, with an
        # operator-only next step and nothing that tells its view, so the record is projected whatever the answer's view.
        return received.model_copy(update={"run_error": caller_view_of(problem=received.run_error)})
    return received


#: The step kind each advice of a report in the former shape names (its `user_action.kind`), in the standard's closed
#: list of kinds; an advice of another kind, `unknown` included, takes its code's.
_FORMER_ADVICE_KINDS: dict[str, StepKind] = {
    "wait_and_retry": StepKind.WAIT,
    "check_billing": StepKind.CHECK_ACCOUNT,
    "check_credentials": StepKind.CHECK_CREDENTIALS,
    "change_input": StepKind.CHANGE_INPUT,
    "change_model": StepKind.CHANGE_MODEL,
    "contact_support": StepKind.REPORT,
}


def _stored_run_problem(*, report: RunErrorReport | None) -> PipelexProblem | None:
    """The failed run's own problem, read off the report the hosted API stored for it; ``None`` when it stored none.

    A report that is a problem document is read as a runner's answer is (:func:`received_problem`), in the caller's
    view, so a member it holds beside the problem, such as its `message` or its `error_type`, is left out, and so is one
    of Pipelex's members that does not read, never the whole problem. A report in the shape the hosted plane wrote before
    it stored problem documents is read by :func:`_former_run_problem`.
    """
    if report is None:
        return None
    try:
        stored = Problem.model_validate(report.model_dump(mode="json", exclude_none=True))
    except ValidationError:
        return _former_run_problem(report=report)
    return received_problem(problem=stored, stored=True)


def _former_run_problem(*, report: RunErrorReport) -> PipelexProblem:
    """The failed run's own problem, read off a report in the shape the hosted plane wrote before it stored problem documents.

    Such a report names no code: one that lists validation items is `method.invalid`, its items coded as a local verdict
    codes them (:func:`hosted_method_problem_items`), and any other is `runtime.unexpected` (:func:`_former_problem`).
    Its `error_category`, `model` and `provider` are not carried: neither code declares a parameter for them, and the
    hosted read's projection drops the model and the provider.
    """
    advice = report.user_action
    return _former_problem(
        validation_errors=report.validation_errors or [],
        message=report.message,
        advice_kind=advice.kind if advice is not None else None,
        advice_detail=advice.detail if advice is not None else None,
        retryable=report.retryable,
    )


def _former_refusal_problem(*, error: ApiResponseError) -> PipelexProblem | None:
    """A refusal in the shape that predates the standard's that lists validation items: the method sent does not validate.

    A runner answered `/v1/start` and `/v1/execute` so before it answered problem documents, and the standard's client
    reads such an answer by its status alone. It is `method.invalid`, read as a stored report in the same shape is
    (:func:`_former_problem`), with the answer's reason, advice and retry verdict, its status and its request id, so
    this CLI lists what the human CLI lists (`describe_hosted_error`).

    Returns:
        The problem, or ``None`` when the answer lists no item or is not in that shape
        (`pipelex.hosted.error_rendering.answered_in_former_shape`).
    """
    if not error.validation_errors or not answered_in_former_shape(error=error):
        return None
    advice = error.user_action
    problem = _former_problem(
        validation_errors=error.validation_errors,
        message=error.server_message,
        advice_kind=advice.kind if advice is not None else None,
        advice_detail=advice.detail if advice is not None else None,
        retryable=sent_verdict(error=error).retryable,
    )
    updates: dict[str, Any] = {"status": error.status}
    if error.request_id:
        updates["request_id"] = error.request_id
    return problem.model_copy(update=updates)


def _former_problem(
    *,
    validation_errors: list[SentValidationErrorItem],
    message: str | None,
    advice_kind: str | None,
    advice_detail: str | None,
    retryable: bool | None,
) -> PipelexProblem:
    """The problem a report or an answer in the shape that predates the standard's makes, in the caller's view.

    It names no code: one that lists validation items is `method.invalid`, its items coded as a local verdict codes them
    (:func:`hosted_method_problem_items`), and any other is `runtime.unexpected`. Its message is the problem's detail,
    its advice the next step, of the kind :data:`_FORMER_ADVICE_KINDS` reads, and its `retryable` the retry verdict, so
    this CLI tells what the human CLI tells of the same failure (`describe_hosted_error`).
    """
    items = hosted_method_problem_items(validation_errors=validation_errors)
    problem = make_problem(code=CoreCode.METHOD_INVALID if items else CoreCode.RUNTIME_UNEXPECTED, view=ProblemView.CALLER, errors=items or None)
    updates: dict[str, Any] = {}
    if message:
        updates["detail"] = message
    if advice_detail:
        updates["next_step"] = NextStep(kind=_FORMER_ADVICE_KINDS.get(advice_kind or "", problem.next_step.kind), detail=advice_detail)
    if isinstance(retryable, bool):
        updates["retry"] = RetryVerdict.YES if retryable else RetryVerdict.NO
    return problem.model_copy(update=updates)


def _typed_sent_item(*, sent: SentValidationErrorItem) -> ValidationErrorItem:
    """A validation item the hosted API sent, typed as this version reads one, by the fields this version declares.

    A field this version does not declare is left out, so an item of a type it reads keeps its type. An item of a
    newer runner whose declared fields this version does not read, such as a type it does not know, keeps its
    locators, and its sentence becomes the finding of the item no stage classified.
    """
    sent_fields = sent.model_dump(mode="json", exclude_none=True)
    declared = {name: value for name, value in sent_fields.items() if name in ValidationErrorItem.model_fields}
    try:
        return ValidationErrorItem.model_validate(declared)
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


def hosted_failure_problem(*, error: PipelineRequestError | HostedRunError, credential_sent: bool) -> PipelexProblem:
    """The problem of a run on a runner that failed, in the caller's view: the runner's, the client's, or pipelex's own.

    - A refusal the runner answered, a runner that cannot be reached and every other failure the client meets carries
      the problem the standard's client decided (`exc.problem`), reported as it came (:func:`received_problem`): the
      runner's own problem document when the answer is one, and otherwise the code the client reads, such as
      `client.unreachable` naming the base URL, or `client.outcome_unknown` for an answer that leaves a run possibly
      started, a server fault on the run request included.
      A failure the client met on its own side takes the step the human CLI tailors for it in place of its code's
      (`pipelex.hosted.error_rendering.tailored_next_step`).
    - An answer in a shape that predates the standard's, which the standard's client reads by its status alone, reads
      as the core code its status and the hosted plane's own code name, with the next step the human CLI gives
      (`pipelex.hosted.error_rendering.hosted_refusal_problem`): a refused or missing credential, a refused operation, a
      route, run or method this origin does not serve, a rate limit with its delay; one listing validation items is
      `method.invalid` with those items, as a stored report in the same shape is (:func:`_former_refusal_problem`);
      and any other such answer keeps the client's reading with the reason the answer gave.
    - A run that started and failed is `run.failed`, naming the run and its status, and nests the run's own problem as
      `run_error`, read off the report the hosted API stored for it, whatever its shape.
    - A failure pipelex detects itself is its `HostedRunError`'s problem, naming the run the hosted API acknowledged
      when there is one, and a method the hosted API found does not load lists the hosted API's items as `errors`.

    Args:
        error: The failure.
        credential_sent: Whether the run's requests carried a key, which tells a refused key from a missing one.

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
    request_id: str | None = None
    if isinstance(error, ApiResponseError):
        refusal = _former_refusal_problem(error=error) or hosted_refusal_problem(error=error, credential_sent=credential_sent)
        if refusal is not None:
            return refusal
        request_id = error.request_id
    problem = received_problem(problem=error.problem, request_id=request_id)
    if isinstance(error, RunFailedError):
        # The run's own step rides in its nested problem.
        run_error = _stored_run_problem(report=error.error)
        return problem.with_members(run_error=run_error.to_wire()) if run_error is not None else problem
    tailored = None if isinstance(error, ApiResponseError) else tailored_next_step(error=error)
    if tailored is not None:
        problem = problem.model_copy(update={"next_step": NextStep(kind=problem.next_step.kind, detail=tailored)})
    return problem


def agent_error_hosted(*, error: PipelineRequestError | HostedRunError, credential_sent: bool, exit_code: int = 1) -> NoReturn:
    """Report a run on a runner that failed as its problem (:func:`hosted_failure_problem`), and exit with `exit_code`.

    The problem is printed as it came, in the active error format, with no member of the envelope this CLI wrote before
    it reported problems. pipelex's own errors add their sentence as `message`, and so does every error of pipelex-sdk's
    own, which says what its code's parameters cannot: the stored reason of a run that failed, how long the client waited
    for one that did not finish, that a completed run delivered no main output. An answer's refusal and a runner that
    cannot be reached add none, their problem saying it all, where their sentence would quote a raw body or a transport's
    class. The usage statistics record what the problem says, except for a refusal a server answered, which they record
    by the code and domain its body sent alone, and not at all when it sent none, never by the client's reading of its status.
    """
    problem = hosted_failure_problem(error=error, credential_sent=credential_sent)
    message: str | None
    if isinstance(error, PipelexError):
        message = error.message
    elif isinstance(error, PipelexRequestError) and not isinstance(error, ApiResponseError | ApiUnreachableError):
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
