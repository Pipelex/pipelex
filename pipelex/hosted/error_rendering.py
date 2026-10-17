"""What went wrong on a hosted run, and what to do next, read off the error pipelex-sdk or pipelex raised.

Every error of a hosted run that is not pipelex's own arrives as one of the SDK's classes, all of which derive from
the protocol's `PipelineRequestError`; pipelex's own derive from `HostedRunError`. An `ApiResponseError` carries the
hosted API's problem document: its reason (the problem's `detail`) and, when the server advised one, its next step
(`user_action.detail`). Answers the hosted plane authors in front of the runner (a refused key, an unknown route, a
rate limit, an unavailable runner) advise none, so their next step follows their status here. The human CLI prints
this view of an error, its run id and its validation items included; the agent CLI reports the problem the error
carries instead (`pipelex/cli/agent_cli/commands/run/_run_hosted.py`), except for a refusal the hosted plane answered
in its own shape, which predates the standard's problem document: `hosted_refusal_problem` reads that one as the core
code its status names, with the next step this module gives the human CLI, so both CLIs tell the same thing.
"""

import math
from typing import Any, NamedTuple

from mthds.protocol.exceptions import PipelineRequestError
from mthds.protocol.problem.answers import parse_retry_after, read_problem_document
from mthds.protocol.problem.client_problems import render_template
from mthds.protocol.problem.registry import CoreCode
from pipelex_sdk.errors import (
    ApiResponseError,
    ApiUnreachableError,
    InputPreparationError,
    InvalidLocalSourceError,
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
from pydantic import ValidationError

from pipelex.base_exceptions import ErrorDomain
from pipelex.errors.error_codes import error_code_spec
from pipelex.errors.problem import PipelexProblem
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


#: The member of the hosted plane's own refusal that states, in seconds, how long to wait before asking again; its
#: `Retry-After` header states it too, and wins.
_SENT_RETRY_AFTER_MEMBER = "retry_after_seconds"


def _hosted_refusal_code(*, status: int, credential_sent: bool) -> CoreCode | None:
    """The core code a refusal of the hosted plane in its own shape reads as, by its status; ``None`` for a status none names.

    A refused credential is the hosted plane's `unauthorized` (`401`) and the refusals of its gateway and of its roles
    (`403`), which its next step tells apart; it is `auth.missing_credential` when the request carried no key. Its
    `not_found` (`404`) is a route or a method this origin does not serve, and its `rate_limited` (`429`) a rate limit.
    """
    match status:
        case 401 | 403:
            return CoreCode.AUTH_INVALID_CREDENTIAL if credential_sent else CoreCode.AUTH_MISSING_CREDENTIAL
        case 404:
            return CoreCode.REQUEST_NOT_FOUND
        case 429:
            return CoreCode.ACCOUNT_RATE_LIMITED
        case _:
            return None


def _sent_retry_after(*, error: ApiResponseError) -> float | None:
    """How long the hosted plane said to wait, in seconds: its `Retry-After` header, else its body's own member."""
    from_header = parse_retry_after((error.headers or {}).get("retry-after"))
    if from_header is not None:
        return from_header
    sent = (error.problem_document or {}).get(_SENT_RETRY_AFTER_MEMBER)
    if isinstance(sent, int | float) and not isinstance(sent, bool) and math.isfinite(sent) and sent >= 0:
        return sent
    return None


def hosted_refusal_problem(*, error: ApiResponseError, credential_sent: bool) -> PipelexProblem | None:
    """A refusal the hosted plane answered in its own shape, as the problem the standard's code for its status states.

    The hosted plane answers its own refusals in a shape that predates the standard's problem document (a closed `code`
    such as `unauthorized` or `rate_limited`, beside `error_domain` and `retryable`), which the standard's client reads
    only by its status, and for these statuses as `client.response_unreadable`, losing what to do. Such a refusal reads
    as the core code its status names (:func:`_hosted_refusal_code`), in the caller's view: the plane's own `detail` kept
    as the problem's, the next step the human CLI gives (:func:`hosted_refusal_next_step`, the one the plane advised
    when it advised one), its request id, and for a rate limit the delay its `Retry-After` header or its body states.

    Args:
        error: The refusal, as the client raised it.
        credential_sent: Whether the request carried a key, which tells a refused key from a missing one.

    Returns:
        The problem, or ``None`` when the answer is a problem document of the standard, which speaks for itself, or
        carries a status no core code here names.
    """
    if read_problem_document(error.response_body, status=error.status, headers=error.headers or {}) is not None:
        return None
    code = _hosted_refusal_code(status=error.status, credential_sent=credential_sent)
    if code is None:
        return None
    spec = error_code_spec(code)
    detail = error.server_message
    if not detail:
        try:
            detail = render_template(spec.detail, params={})
        except ValueError:
            # The code's sentence names parameters the plane's answer does not give, such as a rate's limit and window.
            detail = spec.title
    members: dict[str, Any] = {
        "type": spec.type_uri,
        "title": spec.title,
        "status": error.status,
        "detail": detail,
        "code": spec.code,
        "domain": spec.domain,
        "retry": spec.retry,
        "next_step": {"kind": spec.actor_step, "detail": hosted_refusal_next_step(error=error)},
    }
    # A problem never writes a member as null, so a member with no value is left out.
    retry_after = _sent_retry_after(error=error) if spec.invites_retry else None
    if retry_after is not None:
        members["retry_after"] = retry_after
    if error.request_id:
        members["request_id"] = error.request_id
    try:
        return PipelexProblem.model_validate(members)
    except ValidationError:
        # A member the plane sent that the problem cannot hold, such as an empty next step it advised: the standard's
        # client's own reading of the answer stands.
        return None


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
            next_step = error.user_action.detail if error.user_action is not None else "Check the run request: the method, the pipe and the inputs"
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
            next_step = "Check the run request: the method, the pipe and the inputs"
    return HostedErrorView(
        error_type=error_type,
        message=message,
        next_step=next_step,
        error_domain=error_domain,
        retryable=retryable,
        pipeline_run_id=pipeline_run_id,
        validation_errors=validation_errors,
    )
