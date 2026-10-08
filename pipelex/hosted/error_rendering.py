"""What went wrong on a hosted run, and what to do next, read off the error pipelex-sdk or pipelex raised.

Every error of a hosted run that is not pipelex's own arrives as one of the SDK's classes, all of which derive from
the protocol's `PipelineRequestError`; pipelex's own derive from `HostedRunError`. An `ApiResponseError` carries the
hosted API's problem document: its reason (the problem's `detail`) and, when the server advised one, its next step
(`user_action.detail`). Answers the hosted plane authors in front of the runner (a refused key, an unknown route, a
rate limit, an unavailable runner) advise none, so their next step follows their status here. Both CLIs read the
same view of an error, its run id and its validation items included, so a person and an agent are told the same
thing.
"""

from typing import NamedTuple

from mthds.protocol.exceptions import PipelineRequestError
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

from pipelex.base_exceptions import ErrorDomain
from pipelex.hosted.client_factory import HOSTED_API_DEFAULT_BASE_URL, PIPELEX_API_KEY_ENV_KEY, PIPELEX_BASE_URL_ENV_KEY
from pipelex.hosted.exceptions import HostedMethodInvalidError, HostedRunError, HostedRunInterruptedError, HostedRunPollingError

#: Where a hosted run takes its key from, and where a person gets one.
HOSTED_API_KEY_NEXT_STEP = (
    f"Set {PIPELEX_API_KEY_ENV_KEY} to a Pipelex API key (plx_sk_…) in your shell or in ~/.pipelex/.env; create one on app.pipelex.com"
)
#: Where a hosted run takes its origin from.
HOSTED_BASE_URL_NEXT_STEP = (
    f"Check the hosted API origin: --base-url, else {PIPELEX_BASE_URL_ENV_KEY}, else https://api.pipelex.com; "
    "it is scheme://host[:port], with no path such as /v1"
)
_RATE_LIMITED_NEXT_STEP = "Too many requests: wait retry_after_seconds when the error carries it, otherwise a few seconds, then run again"
# A 503 does not say whether the run happened: the hosted plane can answer it before forwarding the request and also
# after the run completed, when it failed to record the result. So its next step warns that running again can repeat
# a paid run.
_UNAVAILABLE_NEXT_STEP = (
    "The hosted API or the runner behind it was unavailable. It may have failed before the run or after it, so running "
    "again can repeat a paid run: wait retry_after_seconds when the error carries it, then run again only if a repeated run is acceptable"
)

#: The next step of a refusal whose answer advised none, by its HTTP status.
HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS: dict[int, str] = {
    401: f"The hosted API refused the credentials. {HOSTED_API_KEY_NEXT_STEP}",
    403: (
        f"The hosted API refused the request: check that {PIPELEX_API_KEY_ENV_KEY} is a valid key for the API at "
        f"{PIPELEX_BASE_URL_ENV_KEY} (or --base-url); when it is, the message says what this request may not do"
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
            error_domain = error.error_domain
            if isinstance(error, (HostedRunPollingError, HostedRunInterruptedError)):
                pipeline_run_id = error.pipeline_run_id
            if isinstance(error, HostedMethodInvalidError):
                validation_errors = tuple(error.validation_errors)
        case ApiResponseError():
            error_type = error.error_type or error_type
            message = hosted_refusal_message(error=error)
            next_step = hosted_refusal_next_step(error=error)
            error_domain = error.error_domain
            retryable = error.retryable
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
