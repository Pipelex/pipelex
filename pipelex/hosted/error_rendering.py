"""What went wrong on a hosted run, and what to do next: the problem both CLIs report, read off the error pipelex-sdk or pipelex raised.

Every error of a hosted run that is not pipelex's own arrives as one of pipelex-sdk's classes, all of which derive from
the protocol's `PipelineRequestError` and carry the failure as the standard's problem document (`exc.problem`): the
runner's own when it answered one, and otherwise the code the client states. pipelex's own derive from `HostedRunError`
and give theirs (:meth:`PipelexError.to_problem`). The problem is reported as it came, in the caller's view, since the
runner is someone else's runtime (:func:`received_problem`), with two readings of this client's own
(:func:`hosted_failure_problem`):

- an answer that is no problem document, the bare answer of the hosted edge, a gateway or a proxy, which pipelex-sdk
  reads by its status alone, is read here too: a refused credential is a missing one when the request carried no key,
  and a refused credential or a route the server does not serve takes the next step that names this client's settings.
  This reading stays written by hand until the registry records it and every client generates it;
- a failure the client met on its own side, such as a runner that cannot be reached, a run past the wait or a file that
  could not be uploaded, takes the next step this client tailors for it, naming its settings and the run.

Both CLIs report the same problem (:func:`describe_hosted_error`): the agent CLI prints it as JSON or Markdown
(`pipelex/cli/agent_cli/commands/run/_run_hosted.py`), the human CLI as the rows of its failure panels
(`pipelex/cli/commands/run/_run_hosted.py`), each with the error's own sentence and pipelex's own advice beside it.
"""

from collections.abc import Mapping
from typing import Any, NamedTuple, cast

from mthds.protocol.exceptions import PipelineRequestError
from mthds.protocol.problem.answers import read_problem_document
from mthds.protocol.problem.models import NextStep, Problem, ProblemItem, ProblemLocation, SuggestedFix
from mthds.protocol.problem.registry import CoreCode, RetryVerdict
from pipelex_sdk.errors import (
    ApiResponseError,
    ApiUnreachableError,
    InputPreparationError,
    InvalidLocalSourceError,
    MethodFileTransferError,
    MethodFileTransferReason,
    MissingMainStuffError,
    PipelexRequestError,
    PipelineExecuteTimeoutError,
    RejectedAssetError,
    RunLifecycleUnavailableError,
    RunTimeoutError,
    UnsupportedUploadCapabilityError,
    UploadAuthenticationError,
    UploadTransportError,
    UploadTransportReason,
)
from pydantic import BaseModel, ValidationError

from pipelex.base_exceptions import PipelexError
from pipelex.errors.problem import PipelexProblem, ProblemView, caller_view_of, make_problem
from pipelex.hosted.client_factory import HOSTED_API_DEFAULT_BASE_URL, PIPELEX_API_KEY_ENV_KEY, PIPELEX_BASE_URL_ENV_KEY
from pipelex.hosted.exceptions import HostedMethodInvalidError, HostedRunError, HostedRunInterruptedError, HostedRunPollingError

#: The command that gets a Pipelex API key and saves it where a hosted run reads it.
PIPELEX_LOGIN_COMMAND = "pipelex login"
#: Where a hosted run takes its key from, and how a person gets one. The runtime loads the home `.env`, then the working
#: directory's, each over the environment, so a key exported in the shell cannot replace one either file sets.
HOSTED_API_KEY_NEXT_STEP = (
    f"Run {PIPELEX_LOGIN_COMMAND} to get a Pipelex API key (plx_sk_…) and save it to ~/.pipelex/.env as {PIPELEX_API_KEY_ENV_KEY}. "
    f"A .env in the working directory that sets {PIPELEX_API_KEY_ENV_KEY} wins over that file, so correct or remove the line there; "
    f"a key exported in your shell is used only when neither .env file sets {PIPELEX_API_KEY_ENV_KEY}"
)
#: Where a hosted run takes its origin from.
HOSTED_BASE_URL_NEXT_STEP = (
    f"Check the hosted API origin: --base-url, else {PIPELEX_BASE_URL_ENV_KEY}, else https://api.pipelex.com; "
    "it is scheme://host[:port], with no path such as /v1"
)

#: The next step of a request refused because it carried no key, which the hosted edge answers with a bare 401 or 403.
HOSTED_MISSING_KEY_NEXT_STEP = f"The request carried no Pipelex API key. {HOSTED_API_KEY_NEXT_STEP}"
#: The next step of an answer that is no problem document, by its HTTP status, for the statuses this client reads.
HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS: dict[int, str] = {
    401: f"The hosted API refused the credentials. {HOSTED_API_KEY_NEXT_STEP}",
    403: (
        f"The hosted API refused the request's key: check that {PIPELEX_API_KEY_ENV_KEY} is a valid key for the API at "
        f"{PIPELEX_BASE_URL_ENV_KEY} (or --base-url), and run {PIPELEX_LOGIN_COMMAND} to replace it when it is not; "
        "a valid key may also be refused a route it may not call"
    ),
    404: f"The server at the base URL serves no such route. {HOSTED_BASE_URL_NEXT_STEP}",
}
#: The next step of a request that never reached the hosted API.
HOSTED_UNREACHABLE_NEXT_STEP = f"Check the network connection. {HOSTED_BASE_URL_NEXT_STEP}"
#: The next steps of a file of the method's tree that could not be moved to or from the hosted API's storage, by why it
#: failed. pipelex-sdk moves a tree's files before the request that needs them, so nothing was started.
HOSTED_FILE_UNREACHABLE_NEXT_STEP = (
    "The hosted API's storage gave no answer for a file of the method, so nothing was started: check the network connection, then run again"
)
HOSTED_FILE_STORAGE_ERROR_NEXT_STEP = (
    "The hosted API's storage failed, timed out or throttled a file of the method, so nothing was started: wait a few seconds, then run again"
)
HOSTED_FILE_MISMATCH_NEXT_STEP = (
    "A file of the method came back from the hosted API's storage as other bytes than the ones it names: report it with the SHA-256 the message names"
)
HOSTED_FILE_REFUSED_NEXT_STEP = (
    "The hosted API's storage refused a file of the method, so nothing was started, and running again meets the same refusal: "
    "report it with the SHA-256 the message names"
)

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


def received_problem(*, problem: Problem, request_id: str | None = None) -> PipelexProblem:
    """A problem a runner answered or a client decided, as both CLIs report it: as it came, in the caller's view.

    A runner answers its caller in the caller's view already, so the problem is kept as it came, the runner's own next
    step included, by the members the standard and Pipelex declare alone (:func:`_readable_problem`): a member no reader
    declares, such as the `error_type`, `error_domain` and `retryable` a runner may still write, is left out at every
    level, and one of Pipelex's members that does not read is left out alone. An answer that carries diagnostics, which
    a runner answers only to its operator, is projected onto the caller's view (:func:`caller_view_of`), decided from
    the document as it came, before any member is left out, since this machine is not the runner's operator; so is the
    failed run's own problem an answer nests (`run_error`), which is the run's stored record, in its operator's view,
    whatever view the answer around it is in.

    The reading never fails: a problem the standard's client validated always makes one, and the last resort for one
    that would not is `runtime.unexpected`, so the command always prints a problem.

    Args:
        problem: The problem as the standard's client reads it.
        request_id: The request the answer belongs to, when the client read it off the answer and the problem names none.

    Returns:
        The problem, in the caller's view.
    """
    members = problem.as_wire()
    received = _readable_problem(members=members)
    if received is None:
        return make_problem(code=CoreCode.RUNTIME_UNEXPECTED, view=ProblemView.CALLER, request_id=request_id)
    if request_id and received.request_id is None:
        received = received.model_copy(update={"request_id": request_id})
    if _holds_diagnostics(members=members):
        return caller_view_of(problem=received)
    if received.run_error is not None:
        # A runner's caller-view answer may still nest the run's record as it was stored, in its operator's view, with an
        # operator-only next step and nothing that tells its view, so the record is projected whatever the answer's view.
        return received.model_copy(update={"run_error": caller_view_of(problem=received.run_error)})
    return received


class _BareAnswerReading(NamedTuple):
    """The code an answer that is no problem document reads as here, and the next step that names this client's settings."""

    code: CoreCode
    next_step: str


def _bare_answer_reading(*, status: int, credential_sent: bool) -> _BareAnswerReading | None:
    """The reading of an answer that is no problem document by its status, for the statuses this client reads itself.

    pipelex-sdk reads the hosted edge's bare `401` as `auth.missing_credential`, since the edge answers it to a request
    that carries no key, and its bare `403` as `auth.invalid_credential`: this client knows whether the request carried
    a key, so either is `auth.missing_credential` when none was sent and `auth.invalid_credential` when one was. A bare
    `404` is `request.not_found`: the server at the base URL serves no such route.

    Returns:
        The reading, or ``None`` for a status whose reading by pipelex-sdk stands, with its code's own next step.
    """
    match status:
        case 401 | 403 if not credential_sent:
            return _BareAnswerReading(code=CoreCode.AUTH_MISSING_CREDENTIAL, next_step=HOSTED_MISSING_KEY_NEXT_STEP)
        case 401 | 403:
            return _BareAnswerReading(code=CoreCode.AUTH_INVALID_CREDENTIAL, next_step=HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[status])
        case 404:
            return _BareAnswerReading(code=CoreCode.REQUEST_NOT_FOUND, next_step=HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[404])
        case _:
            return None


def _answered_problem(*, error: ApiResponseError, credential_sent: bool) -> PipelexProblem:
    """The problem of an answer the hosted API, or a server in front of it, gave: the body's own, or this client's reading.

    A body that is a problem document is the runner's own problem, reported as it came (:func:`received_problem`),
    with the request id the answer names. Any other body is the bare answer of the hosted edge, a gateway or a proxy,
    which pipelex-sdk reads by its status alone: an answer that may have started a run keeps its reading as
    `client.outcome_unknown`, and a status this client reads itself (:func:`_bare_answer_reading`) reads as that code,
    with the next step that names this client's settings; any other keeps pipelex-sdk's reading.
    """
    received = received_problem(problem=error.problem, request_id=error.request_id)
    if read_problem_document(error.response_body, status=error.status, headers=error.headers or {}) is not None:
        return received
    match received.effective_retry:
        case RetryVerdict.OUTCOME_UNKNOWN:
            return received
        case RetryVerdict.YES | RetryVerdict.NO:
            pass
    reading = _bare_answer_reading(status=error.status, credential_sent=credential_sent)
    if reading is None:
        return received
    problem = make_problem(code=reading.code, view=ProblemView.CALLER, request_id=error.request_id)
    return problem.model_copy(update={"status": error.status, "next_step": NextStep(kind=problem.next_step.kind, detail=reading.next_step)})


def _upload_transport_next_step(*, reason: UploadTransportReason | None) -> str | None:
    """The next step of an upload of an input's file that met a transport failure, ``None`` where its code's own fits."""
    match reason:
        case UploadTransportReason.TIMEOUT | UploadTransportReason.UNREACHABLE:
            return HOSTED_UNREACHABLE_NEXT_STEP
        case (
            UploadTransportReason.SERVER_ERROR
            | UploadTransportReason.STORAGE_TIMEOUT
            | UploadTransportReason.CONFLICT
            | UploadTransportReason.REDIRECTED
            | UploadTransportReason.INVALID_GRANT_URL
            | UploadTransportReason.UNEXPECTED
            | None
        ):
            return None


def _method_file_transfer_next_step(*, reason: MethodFileTransferReason) -> str:
    """The next step of a file of the method's tree that could not be moved, by why it failed.

    Running again is the step for a reason pipelex-sdk reads as `runtime.unavailable`, which a later attempt can pass,
    and the others are reported, since storage gives the same answer to the same upload.
    """
    match reason:
        case MethodFileTransferReason.UNREACHABLE:
            return HOSTED_FILE_UNREACHABLE_NEXT_STEP
        case MethodFileTransferReason.STORAGE_ERROR:
            return HOSTED_FILE_STORAGE_ERROR_NEXT_STEP
        case MethodFileTransferReason.MISMATCH:
            return HOSTED_FILE_MISMATCH_NEXT_STEP
        case MethodFileTransferReason.REFUSED:
            return HOSTED_FILE_REFUSED_NEXT_STEP


def tailored_next_step(*, error: PipelineRequestError) -> str | None:
    """The next step this client tailors for a failure it met on its own side, ``None`` where its code's own step fits.

    The step names this client's settings and the run it means, which the code's own step, written for every client,
    cannot. An answer the hosted API gave is read apart (:func:`_answered_problem`), and a run that started and failed
    keeps its code's step, which points at the run's own problem.
    """
    match error:
        case RunTimeoutError():
            return (
                f"The run {error.run_id} keeps running on the hosted API: find it on app.pipelex.com, or read its result "
                "later with pipelex-sdk's PipelexAPIClient.wait_for_result"
            )
        case MissingMainStuffError():
            return (
                f"The run {error.run_id} completed, but the hosted API delivered no main output: look the run up by its id on "
                "app.pipelex.com, and report it with the run id"
            )
        case PipelineExecuteTimeoutError():
            # A hosted run calls the blocking route only on a server that keeps no runs (its version handshake says so,
            # or its start refused for a missing run store), so running again takes the same route and repeats a paid run.
            return (
                "The server at the base URL keeps no runs to poll, so the run went through the blocking route and the connection "
                "was cut before the result came back. The run may still be going there, and running the command again runs the "
                "method again on the same route: raise the timeout of the proxy in front of that server, or point --base-url or "
                f"{PIPELEX_BASE_URL_ENV_KEY} at a server that keeps runs, such as {HOSTED_API_DEFAULT_BASE_URL}"
            )
        case ApiUnreachableError():
            # A request that may have started a run keeps its code's step, which reads the run rather than sends it again.
            match error.problem.effective_retry:
                case RetryVerdict.OUTCOME_UNKNOWN:
                    return None
                case RetryVerdict.YES | RetryVerdict.NO:
                    return HOSTED_UNREACHABLE_NEXT_STEP
        case RunLifecycleUnavailableError():
            return f"The server at the base URL is a bare runner without run polling. {HOSTED_BASE_URL_NEXT_STEP}"
        case UploadAuthenticationError():
            return HOSTED_API_KEY_NEXT_STEP
        case InvalidLocalSourceError():
            return "Check the file path in the inputs: a relative path in an inputs file resolves against that file's directory"
        case RejectedAssetError():
            return "The hosted API refused the file: send a smaller one, or one of a type the input accepts"
        case UnsupportedUploadCapabilityError():
            return f"The server at the base URL takes no uploads: pass the file as an http(s) URL. {HOSTED_BASE_URL_NEXT_STEP}"
        case UploadTransportError():
            return _upload_transport_next_step(reason=error.reason)
        case InputPreparationError():
            return "Check the inputs against the pipe's signature (pipelex-agent inputs prints a template), then run again"
        case MethodFileTransferError():
            # A file of the method's tree, sent by hash, that could not be uploaded before pipe-io or the run.
            return _method_file_transfer_next_step(reason=error.reason)
        case _:
            return None


def _method_invalid_problem(*, error: HostedMethodInvalidError) -> PipelexProblem:
    """The problem of a method pipe-io's verdict found does not load: `method.invalid`, listing the verdict's items as they came.

    The runner answered its verdict to its caller already, so its items are reported as a runner's own problem is
    (:func:`received_problem`): by the members the standard declares alone, since pipelex-sdk keeps those it does not
    declare as it received them, and never projected onto a view again. A projection would read an item under a code
    this client's registry does not hold, as a runner newer than the client answers, as one whose parameters it cannot
    tell apart, and replace its sentence and its parameters with the generic sentence, losing the runner's explanation.
    """
    head = error.to_problem(view=ProblemView.CALLER)
    verdict_items = [ProblemItem.model_validate(_declared_members(members=item.as_wire(), shape=ProblemItem)) for item in error.errors]
    return head.model_copy(update={"errors": verdict_items or None})


def hosted_failure_problem(*, error: PipelineRequestError | HostedRunError, credential_sent: bool) -> PipelexProblem:
    """The problem of a run on a runner that failed, in the caller's view: the runner's, the client's, or pipelex's own.

    - An answer the hosted API, or a server in front of it, gave is the runner's own problem document when its body is
      one, and otherwise this client's reading of the bare answer (:func:`_answered_problem`).
    - A run that started and failed is `run.failed`, naming the run and its status, and nests the run's own problem as
      `run_error`, projected onto the caller's view (:func:`received_problem`).
    - Every other failure the client met carries the problem it decided, such as `client.unreachable` naming the base
      URL, with the next step this client tailors for it (:func:`tailored_next_step`) in place of its code's.
    - A failure pipelex detects itself is its `HostedRunError`'s problem, naming the run the hosted API acknowledged
      when there is one, and a method the hosted API found does not load lists the verdict's items as its `errors`,
      as they came, by their declared members alone (:func:`_method_invalid_problem`).

    Args:
        error: The failure.
        credential_sent: Whether the run's requests carried a key, which tells a refused key from a missing one.

    Returns:
        The problem, in the caller's view.
    """
    if isinstance(error, HostedRunPollingError | HostedRunInterruptedError):
        return error.to_problem(view=ProblemView.CALLER, pipeline_run_id=error.pipeline_run_id)
    if isinstance(error, HostedMethodInvalidError):
        return _method_invalid_problem(error=error)
    if isinstance(error, HostedRunError):
        return error.to_problem(view=ProblemView.CALLER)
    if isinstance(error, ApiResponseError):
        return _answered_problem(error=error, credential_sent=credential_sent)
    problem = received_problem(problem=error.problem)
    tailored = tailored_next_step(error=error)
    if tailored is None:
        return problem
    return problem.model_copy(update={"next_step": NextStep(kind=problem.next_step.kind, detail=tailored)})


class HostedErrorView(NamedTuple):
    """A hosted run's failure, as both CLIs tell it: its problem, the error's own sentence, and pipelex's own advice.

    `problem` is in the caller's view (:func:`hosted_failure_problem`): its title and its detail, its next step, its
    code with its domain and its retry verdict, the request and the run it names, the faults it lists as its `errors`,
    and, for a run that started and failed, the run's own problem it nests as `run_error`. `message` is the error's own
    sentence when it says what the problem does not, `None` when the problem says it all. `advice` is what pipelex's own
    error advises, which a CLI prints as its tip and no problem carries.
    """

    problem: PipelexProblem
    message: str | None
    advice: str | None


def describe_hosted_error(*, error: PipelineRequestError | HostedRunError, credential_sent: bool) -> HostedErrorView:
    """Read a hosted run's failure off the error pipelex-sdk or pipelex raised, as both CLIs report it.

    pipelex's own errors give their sentence and their advice. Every error of pipelex-sdk's own gives its sentence,
    which says what its code's parameters cannot: the reason a run that failed stored, how long the client waited for
    one that did not finish, that a completed run delivered no main output. An answer's refusal and a runner that
    cannot be reached give none, their problem saying it all, where their sentence would quote a raw body or a
    transport's class, and so does an error of the MTHDS client's.

    Args:
        error: The SDK's error, or one pipelex raised during the run.
        credential_sent: Whether the run's requests carried a key, which tells a refused key from a missing one.

    Returns:
        The problem, the error's own sentence and pipelex's own advice.
    """
    problem = hosted_failure_problem(error=error, credential_sent=credential_sent)
    message: str | None
    advice: str | None
    if isinstance(error, PipelexError):
        message = error.message
        advised_action = error.advised_action()
        advice = advised_action.detail if advised_action is not None else None
    elif isinstance(error, PipelexRequestError) and not isinstance(error, ApiResponseError | ApiUnreachableError):
        message = str(error)
        advice = None
    else:
        message = None
        advice = None
    return HostedErrorView(problem=problem, message=message, advice=advice)
