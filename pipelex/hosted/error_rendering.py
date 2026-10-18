"""What went wrong on a hosted run, and what to do next, read off the error pipelex-sdk or pipelex raised.

Every error of a hosted run that is not pipelex's own arrives as one of the SDK's classes, all of which derive from
the protocol's `PipelineRequestError`; pipelex's own derive from `HostedRunError`. An `ApiResponseError` carries the
hosted API's problem document: its reason (the problem's `detail`) and, when the server advised one, its next step
(`user_action.detail`). Answers the hosted plane authors in front of the runner (a refused key, an unknown route, a
rate limit, an unavailable runner) advise none, so their next step follows their status here. The human CLI prints
this view of an error, its run id and its validation items included; the agent CLI reports the problem the error
carries instead (`pipelex/cli/agent_cli/commands/run/_run_hosted.py`), with the next step this module tailors for a
failure of the client's own (`tailored_next_step`), and for an answer in a shape that predates the standard's problem
document, which the standard's client reads by its status alone, the problem `hosted_refusal_problem` reads from it:
the core code its status and the plane's own code name, or the client's reading with the answer's own reason, with
the next step this module gives the human CLI, so both CLIs tell the same thing.
"""

from typing import Any, NamedTuple

from mthds.protocol.exceptions import PipelineRequestError
from mthds.protocol.problem.answers import parse_retry_after, read_problem_document
from mthds.protocol.problem.models import NextStep, Problem
from mthds.protocol.problem.registry import STATUS_READINGS, CoreCode, StepKind
from pipelex_sdk.errors import (
    ApiResponseError,
    ApiUnreachableError,
    InputPreparationError,
    InvalidLocalSourceError,
    MethodErrorCode,
    MissingMainStuffError,
    PipelineExecuteTimeoutError,
    RejectedAssetError,
    RunFailedError,
    RunLifecycleUnavailableError,
    RunTimeoutError,
    UnsupportedUploadCapabilityError,
    UploadAuthenticationError,
    UploadTransportError,
)
from pipelex_sdk.validation_models import ValidationErrorItem

from pipelex.base_exceptions import ErrorDomain
from pipelex.errors.error_codes import error_code_spec
from pipelex.errors.problem import PipelexProblem, ProblemView, make_problem
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
_RATE_LIMITED_NEXT_STEP = "Too many requests: wait retry_after seconds when the error gives it, otherwise a few seconds, then run again"
# A 503 does not say whether the run happened: the hosted plane can answer it before forwarding the request and also
# after the run completed, when it failed to record the result. So its next step warns that running again can repeat
# a paid run.
_UNAVAILABLE_NEXT_STEP = (
    "The hosted API or the runner behind it was unavailable. It may have failed before the run or after it, so running "
    "again can repeat a paid run: wait retry_after seconds when the error gives it, then run again only if a repeated run is acceptable"
)

#: The next step of a request refused because it carried no key, which the hosted plane answers with a 401 or a 403.
HOSTED_MISSING_KEY_NEXT_STEP = f"The request carried no Pipelex API key. {HOSTED_API_KEY_NEXT_STEP}"
#: The next step of a 403 the platform answers itself, for a key it authenticated and an operation the key may not do.
HOSTED_FORBIDDEN_NEXT_STEP = (
    "The hosted API accepted the key and refused what this request does: the message says what it may not do. Ask the "
    "organization's owner for that access, or use a key of an account that has it"
)

#: The next step of a refusal whose answer advised none, by its HTTP status.
HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS: dict[int, str] = {
    401: f"The hosted API refused the credentials. {HOSTED_API_KEY_NEXT_STEP}",
    403: (
        f"The hosted API refused the request: check that {PIPELEX_API_KEY_ENV_KEY} is a valid key for the API at "
        f"{PIPELEX_BASE_URL_ENV_KEY} (or --base-url), and run {PIPELEX_LOGIN_COMMAND} to replace it when it is not; "
        "when it is, the message says what this request may not do"
    ),
    404: f"The hosted API has no such method or route: check the method's address or catalog id. {HOSTED_BASE_URL_NEXT_STEP}",
    429: _RATE_LIMITED_NEXT_STEP,
    503: _UNAVAILABLE_NEXT_STEP,
}
#: The next step of a 4xx refusal that advised none and whose status has no next step of its own.
HOSTED_REFUSAL_CALLER_NEXT_STEP = (
    "The hosted API refused the request: change what the message names (the method, the inputs or the configuration), then run again"
)
#: The next step of a server-side failure that advised none.
HOSTED_SERVER_FAULT_NEXT_STEP = (
    "The hosted API failed on its side: report it with the request_id, or with the http_status when the error carries no request_id"
)
#: The next step of a request that never reached the hosted API.
HOSTED_UNREACHABLE_NEXT_STEP = f"Check the network connection. {HOSTED_BASE_URL_NEXT_STEP}"
#: The next step of a failure no arm of `describe_hosted_error` tailors a step for.
HOSTED_RUN_REQUEST_NEXT_STEP = "Check the run request: the method, the pipe and the inputs"


#: The member of the hosted plane's own refusal that states, in seconds, how long to wait before asking again; its
#: `Retry-After` header states it too, and wins.
_SENT_RETRY_AFTER_MEMBER = "retry_after_seconds"
#: The codes the platform answers a `403` with when it authenticated the key and refuses the operation: `forbidden`, and
#: `role_not_permitted` for a role that may not do it. pipelex-sdk names no constant for them. Any other code on a `403`
#: is no refusal of an operation this client can tell, so it reads as the credential's.
_PLANE_AUTHORIZATION_CODES: frozenset[str] = frozenset({"forbidden", "role_not_permitted"})

#: The step kind each advice of an answer or a report in the former shape names (its `user_action.kind`), in the
#: standard's closed list of kinds; an advice of another kind, `unknown` included, takes the kind its reader gives.
FORMER_ADVICE_KINDS: dict[str, StepKind] = {
    "wait_and_retry": StepKind.WAIT,
    "check_billing": StepKind.CHECK_ACCOUNT,
    "check_credentials": StepKind.CHECK_CREDENTIALS,
    "change_input": StepKind.CHANGE_INPUT,
    "change_model": StepKind.CHANGE_MODEL,
    "contact_support": StepKind.REPORT,
}


class _RefusalReading(NamedTuple):
    """The core code a refusal of the hosted plane in its own shape reads as, and the step for it when the plane advised none.

    `next_step` is `None` when the code's own step, from the registry, fits the refusal better than its status's.
    """

    code: CoreCode
    next_step: str | None


def _hosted_refusal_reading(*, status: int, plane_code: str | None, credential_sent: bool) -> _RefusalReading | None:
    """The core code a refusal of the hosted plane in its own shape reads as, by its status and its own code.

    A refused credential is the hosted plane's `401` and the bare `403` its edge's authorizer answers, without a reason,
    for an unknown key among others; it is `auth.missing_credential` when the request carried no key. A `403` the
    platform answers with one of its authorization codes (:data:`_PLANE_AUTHORIZATION_CODES`) refuses an operation to a
    key it authenticated, and a `403` with any other code, such as one for a key that is invalid or expired, refuses the
    credential. A `404` is the run or the method the platform's code names (`run_not_found`,
    `method_version_not_found`), and otherwise a route or a method this origin does not serve, which the platform's
    `not_found` does not tell apart. A `429` is a rate limit.

    Returns:
        The reading, or ``None`` for a status none names.
    """
    by_status = HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS
    match status:
        case 401 | 403 if not credential_sent:
            return _RefusalReading(code=CoreCode.AUTH_MISSING_CREDENTIAL, next_step=HOSTED_MISSING_KEY_NEXT_STEP)
        case 401:
            return _RefusalReading(code=CoreCode.AUTH_INVALID_CREDENTIAL, next_step=by_status[401])
        case 403 if plane_code in _PLANE_AUTHORIZATION_CODES:
            return _RefusalReading(code=CoreCode.AUTH_FORBIDDEN, next_step=HOSTED_FORBIDDEN_NEXT_STEP)
        case 403:
            return _RefusalReading(code=CoreCode.AUTH_INVALID_CREDENTIAL, next_step=by_status[403])
        case 404:
            match plane_code:
                # The platform's code for a run it holds none of, which pipelex-sdk names no constant for.
                case "run_not_found":
                    return _RefusalReading(code=CoreCode.RUN_NOT_FOUND, next_step=None)
                case MethodErrorCode.METHOD_VERSION_NOT_FOUND:
                    return _RefusalReading(code=CoreCode.METHOD_NOT_FOUND, next_step=by_status[404])
                case _:
                    return _RefusalReading(code=CoreCode.REQUEST_NOT_FOUND, next_step=by_status[404])
        case 429:
            return _RefusalReading(code=CoreCode.ACCOUNT_RATE_LIMITED, next_step=by_status[429])
        case _:
            return None


def _sent_retry_after(*, error: ApiResponseError) -> float | None:
    """How long the hosted plane said to wait, in seconds: its `Retry-After` header, else its body's own member.

    Whether the delay is one a problem can carry, and whether its code invites a retry at all, is :func:`make_problem`'s.
    """
    from_header = parse_retry_after((error.headers or {}).get("retry-after"))
    if from_header is not None:
        return from_header
    sent = (error.problem_document or {}).get(_SENT_RETRY_AFTER_MEMBER)
    if isinstance(sent, int | float) and not isinstance(sent, bool):
        return sent
    return None


def answered_in_former_shape(*, error: ApiResponseError) -> bool:
    """Whether a refusal is an answer in a shape that predates the standard's problem document, read by its status alone.

    An answer that is a problem document of the standard speaks for itself, and one that may have started a run keeps the
    client's reading as `client.outcome_unknown`, so neither is.
    """
    if error.run_may_have_started:
        return False
    return read_problem_document(error.response_body, status=error.status, headers=error.headers or {}) is None


def _client_reading(*, error: ApiResponseError) -> PipelexProblem:
    """The client's reading of a refusal, by the members the standard declares alone.

    A member beside them, such as a `run_error` or `diagnostics` of Pipelex's in a shape no reader takes, is left out, so
    the reading never fails: the members of a problem the client validated always make one.
    """
    standard = {name: value for name, value in error.problem.as_wire().items() if name in Problem.model_fields}
    return PipelexProblem.model_validate(standard)


def hosted_refusal_problem(*, error: ApiResponseError, credential_sent: bool) -> PipelexProblem | None:
    """An answer in a shape that predates the standard's problem document, as the problem the agent CLI reports for it.

    The hosted plane answers its own refusals in that shape (a closed `code` such as `unauthorized` or `rate_limited`,
    beside `error_domain` and `retryable`), and so does a runner for a refusal it authors itself, such as the `422` an
    older runner answers for a reserved input key. The standard's client reads such an answer by its status alone,
    `client.response_unreadable` for most, losing its reason and what to do.

    - A refusal whose status and plane code name a core code (:func:`_hosted_refusal_reading`) reads as that code, in
      the caller's view (:func:`make_problem`), the plane's own `detail` kept, its request id, the delay its
      `Retry-After` header or its body states, and the step it advised, else the step the human CLI gives its status.
    - Any other answer that gives its reason keeps the client's reading, its code and its status, by the standard's
      members alone (:func:`_client_reading`), with that reason as its `detail` and the step the human CLI gives it
      (:func:`hosted_refusal_next_step`), so the reader is told what the body said rather than to report a body it
      never sees. The step's kind is the one the answer's advice names (:data:`FORMER_ADVICE_KINDS`), else
      `change_input` for a `4xx`, a refusal of the caller's request, and the client's reading's for any other status.

    The agent CLI reads an answer that lists validation items before this one is asked, as a method that does not
    validate (`pipelex.cli.agent_cli.commands.run._run_hosted`), since only it codes the items.

    Args:
        error: The refusal, as the client raised it.
        credential_sent: Whether the request carried a key, which tells a refused key from a missing one.

    Returns:
        The problem, or ``None`` when the answer is a problem document of the standard, which speaks for itself, when it
        may have started a run, whose reading as `client.outcome_unknown` stands, when its status is one the standard
        reads as a code, or when it names no core code here and gives no reason.
    """
    if not answered_in_former_shape(error=error):
        return None
    reading = _hosted_refusal_reading(status=error.status, plane_code=error.code, credential_sent=credential_sent)
    if reading is not None:
        return _coded_refusal_problem(error=error, reading=reading)
    if error.status in STATUS_READINGS or not error.server_message:
        return None
    reason_kept = _client_reading(error=error)
    # A refusal of the caller's request asks for a change to it; any other answer is the runtime's to explain. Advice
    # the answer gave is the step's detail, so the step takes the kind that advice names.
    status_kind = StepKind.CHANGE_INPUT if 400 <= error.status < 500 else reason_kept.next_step.kind
    advice = error.user_action
    kind = FORMER_ADVICE_KINDS.get(advice.kind, status_kind) if advice is not None else status_kind
    updates: dict[str, Any] = {
        "status": error.status,
        "detail": error.server_message,
        "next_step": NextStep(kind=kind, detail=hosted_refusal_next_step(error=error)),
    }
    if error.request_id:
        updates["request_id"] = error.request_id
    return reason_kept.model_copy(update=updates)


def _coded_refusal_problem(*, error: ApiResponseError, reading: _RefusalReading) -> PipelexProblem:
    """A refusal of the hosted plane as the core code it reads as, with what the plane said of it (:func:`hosted_refusal_problem`)."""
    problem = make_problem(code=reading.code, view=ProblemView.CALLER, retry_after=_sent_retry_after(error=error), request_id=error.request_id)
    if error.user_action is not None:
        step_detail = error.user_action.detail
    else:
        step_detail = reading.next_step or problem.next_step.detail
    return problem.model_copy(
        update={
            "status": error.status,
            "detail": error.server_message or problem.detail,
            "next_step": NextStep(kind=problem.next_step.kind, detail=step_detail),
        }
    )


def tailored_next_step(*, error: PipelineRequestError) -> str | None:
    """The next step the human CLI tailors for a failure the client met, ``None`` when it gives the generic one.

    The agent CLI reports the problem the client decided for such a failure, whose step its code gives, and takes this
    one in its place where there is one, so both CLIs tell the same thing (:func:`describe_hosted_error`).
    """
    next_step = describe_hosted_error(error=error).next_step
    return None if next_step == HOSTED_RUN_REQUEST_NEXT_STEP else next_step


class SentVerdict(NamedTuple):
    """The `error_domain` and `retryable` a hosted API's problem document carried, each `None` when it sent none."""

    error_domain: str | None
    retryable: bool | None


def sent_verdict(*, error: ApiResponseError) -> SentVerdict:
    """The verdict the hosted API sent with a refusal, read off the problem document it answered.

    pipelex-sdk gives every `ApiResponseError` a decided `error_domain` and `retryable`, filling a member the server
    did not send from its own table by status, which reads every unlabelled 5xx, a 503 included, as retryable. A 503
    does not say whether the run happened (see `_UNAVAILABLE_NEXT_STEP`), and who has to act is only the runner's to
    say, so both CLIs report what the server sent and nothing the SDK inferred. `problem_document` keeps the server's
    members as it sent them; `problem` is the standard's reading of the answer, which may be inferred from the status.
    """
    problem_document = error.problem_document or {}
    sent_domain = problem_document.get("error_domain")
    sent_retryable = problem_document.get("retryable")
    return SentVerdict(
        error_domain=sent_domain if isinstance(sent_domain, str) and sent_domain else None,
        retryable=sent_retryable if isinstance(sent_retryable, bool) else None,
    )


class HostedErrorView(NamedTuple):
    """A hosted run's failure, as both CLIs tell it: the class to branch on, what happened, and what to do next.

    `error_domain` says who acts (`input`: the caller's request; `config`: the key, the base URL or the network;
    `runtime`: the run itself), as the hosted API said it when it did; `retryable` is the hosted API's own verdict,
    `None` when it gave none. `pipeline_run_id` names the run once the hosted API acknowledged it, so a run that failed,
    outlived the wait, was lost on the way or was left running by an interruption can be looked up.
    `validation_errors` are the hosted API's items locating the faults of a method it refused, each naming its file
    when the file was sent under a label.
    """

    error_type: str
    message: str
    next_step: str
    error_domain: str | None = None
    retryable: bool | None = None
    pipeline_run_id: str | None = None
    validation_errors: tuple[ValidationErrorItem, ...] = ()


def hosted_refusal_next_step(*, error: ApiResponseError) -> str:
    """The next step of a refusal: the one the server advised, else the one its status calls for."""
    if error.user_action is not None:
        return error.user_action.detail
    by_status = HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS.get(error.status)
    if by_status is not None:
        return by_status
    if 400 <= error.status < 500:
        return HOSTED_REFUSAL_CALLER_NEXT_STEP
    return HOSTED_SERVER_FAULT_NEXT_STEP


def hosted_refusal_message(*, error: ApiResponseError) -> str:
    """`API POST /v1/start failed (422): <reason>`, the error's own message without the next step it appends."""
    message = str(error)
    if error.user_action is not None:
        message = message.removesuffix(f"\nNext step: {error.user_action.detail}")
    return message


def describe_hosted_error(*, error: PipelineRequestError | HostedRunError) -> HostedErrorView:
    """Read a hosted run's failure off the error pipelex-sdk or pipelex raised.

    Args:
        error: The SDK's error, or one pipelex raised during the run. Its class decides the next step; an
            `ApiResponseError` names the runner's own class when the problem document carries one, and a failed run
            names its stored report's.

    Returns:
        The class to report, the message, the next step, and the run and the validation items when there are any.
    """
    error_type = type(error).__name__
    message = str(error)
    next_step: str
    error_domain: str | None = None
    retryable: bool | None = None
    pipeline_run_id: str | None = None
    validation_errors: tuple[ValidationErrorItem, ...] = ()
    match error:
        case HostedRunError():
            message = error.message
            next_step = error.user_action.detail if error.user_action is not None else HOSTED_RUN_REQUEST_NEXT_STEP
            # Who acts and whether a retry can succeed are the error's code's.
            hosted_code_spec = error_code_spec(error.resolve_error_code())
            error_domain = ErrorDomain.from_problem_domain(hosted_code_spec.domain)
            retryable = hosted_code_spec.invites_retry
            if isinstance(error, (HostedRunPollingError, HostedRunInterruptedError)):
                pipeline_run_id = error.pipeline_run_id
            if isinstance(error, HostedMethodInvalidError):
                validation_errors = tuple(error.validation_errors)
        case ApiResponseError():
            error_type = error.error_type or error_type
            message = hosted_refusal_message(error=error)
            next_step = hosted_refusal_next_step(error=error)
            error_domain, retryable = sent_verdict(error=error)
            validation_errors = tuple(error.validation_errors or ())
        case RunFailedError():
            report = error.error
            pipeline_run_id = error.run_id
            error_domain = ErrorDomain.RUNTIME
            if report is not None:
                error_type = report.error_type or error_type
                error_domain = report.error_domain or error_domain
                retryable = report.retryable
                validation_errors = tuple(report.validation_errors or ())
            if report is not None and report.user_action is not None and report.user_action.detail:
                next_step = report.user_action.detail
            else:
                next_step = f"The run {error.run_id} ended {error.status}: change what the message names, then run again"
        case RunTimeoutError():
            pipeline_run_id = error.run_id
            error_domain = ErrorDomain.RUNTIME
            next_step = (
                f"The run {error.run_id} keeps running on the hosted API: find it on app.pipelex.com, or read its result "
                "later with pipelex-sdk's PipelexAPIClient.wait_for_result"
            )
        case MissingMainStuffError():
            pipeline_run_id = error.run_id
            error_domain = ErrorDomain.RUNTIME
            next_step = (
                f"The run {error.run_id} completed, but the hosted API delivered no main output: look the run up by its id on "
                "app.pipelex.com, and report it with the run id"
            )
        case PipelineExecuteTimeoutError():
            # A hosted run calls the blocking route only on a server that keeps no runs (its version handshake says so,
            # or its start refused for a missing run store), so running again takes the same route and repeats a paid run.
            error_domain = ErrorDomain.RUNTIME
            retryable = False
            next_step = (
                "The server at the base URL keeps no runs to poll, so the run went through the blocking route and the connection "
                "was cut before the result came back. The run may still be going there, and running the command again runs the "
                "method again on the same route: raise the timeout of the proxy in front of that server, or point --base-url or "
                f"{PIPELEX_BASE_URL_ENV_KEY} at a server that keeps runs, such as {HOSTED_API_DEFAULT_BASE_URL}"
            )
        case ApiUnreachableError():
            error_domain = ErrorDomain.CONFIG
            next_step = HOSTED_UNREACHABLE_NEXT_STEP
        case RunLifecycleUnavailableError():
            error_domain = ErrorDomain.CONFIG
            next_step = f"The server at the base URL is a bare runner without run polling. {HOSTED_BASE_URL_NEXT_STEP}"
        case UploadAuthenticationError():
            error_domain = ErrorDomain.CONFIG
            next_step = HOSTED_API_KEY_NEXT_STEP
        case InvalidLocalSourceError():
            error_domain = ErrorDomain.INPUT
            next_step = "Check the file path in the inputs: a relative path in an inputs file resolves against that file's directory"
        case RejectedAssetError():
            error_domain = ErrorDomain.INPUT
            next_step = "The hosted API refused the file: send a smaller one, or one of a type the input accepts"
        case UnsupportedUploadCapabilityError():
            error_domain = ErrorDomain.CONFIG
            next_step = f"The server at the base URL takes no uploads: pass the file as an http(s) URL. {HOSTED_BASE_URL_NEXT_STEP}"
        case UploadTransportError():
            # The SDK raises it for an upload that never reached the hosted API, chained from `ApiUnreachableError`,
            # and for one the hosted API failed on its side, a 5xx.
            if isinstance(error.__cause__, ApiUnreachableError):
                error_domain = ErrorDomain.CONFIG
                next_step = HOSTED_UNREACHABLE_NEXT_STEP
            else:
                error_domain = ErrorDomain.RUNTIME
                next_step = HOSTED_SERVER_FAULT_NEXT_STEP
        case InputPreparationError():
            error_domain = ErrorDomain.INPUT
            next_step = "Check the inputs against the pipe's signature (pipelex-agent inputs prints a template), then run again"
        case _:
            next_step = HOSTED_RUN_REQUEST_NEXT_STEP
    return HostedErrorView(
        error_type=error_type,
        message=message,
        next_step=next_step,
        error_domain=error_domain,
        retryable=retryable,
        pipeline_run_id=pipeline_run_id,
        validation_errors=validation_errors,
    )
