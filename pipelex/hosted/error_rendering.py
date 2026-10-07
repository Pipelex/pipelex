"""What went wrong on a hosted run, and what to do next, read off the error pipelex-sdk raised.

Every error of a hosted run that is not pipelex's own arrives as one of the SDK's classes, all of which derive from
the protocol's `PipelineRequestError`. An `ApiResponseError` carries the hosted API's problem document: its reason
(the problem's `detail`) and, when the server advised one, its next step (`user_action.detail`). Answers the hosted
plane authors in front of the runner (a refused key, an unknown route, a rate limit, an unavailable runner) advise
none, so their next step follows their status here. Both CLIs read the same table, so a person and an agent are
told the same thing.
"""

from typing import NamedTuple

from mthds.protocol.exceptions import PipelineRequestError
from pipelex_sdk.errors import (
    ApiResponseError,
    ApiUnreachableError,
    InputPreparationError,
    InvalidLocalSourceError,
    PipelineExecuteTimeoutError,
    RejectedAssetError,
    RunFailedError,
    RunLifecycleUnavailableError,
    RunTimeoutError,
    UnsupportedUploadCapabilityError,
    UploadAuthenticationError,
)

from pipelex.base_exceptions import ErrorDomain
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY, PIPELEX_BASE_URL_ENV_KEY

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


class HostedErrorView(NamedTuple):
    """A hosted run's failure, as both CLIs tell it: the class to branch on, what happened, and what to do next.

    `error_domain` says who acts (`input`: the caller's request; `config`: the key, the base URL or the network;
    `runtime`: the run itself), as the hosted API said it when it did; `retryable` is the hosted API's own verdict,
    `None` when it gave none.
    """

    error_type: str
    message: str
    next_step: str
    error_domain: str | None = None
    retryable: bool | None = None


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


def describe_hosted_error(*, error: PipelineRequestError) -> HostedErrorView:
    """Read a hosted run's failure off the error pipelex-sdk raised.

    Args:
        error: The SDK's error. Its class decides the next step; an `ApiResponseError` names the runner's own class
            when the problem document carries one, and a failed run names its stored report's.

    Returns:
        The class to report, the message, and the next step.
    """
    error_type = type(error).__name__
    message = str(error)
    next_step: str
    error_domain: str | None = None
    retryable: bool | None = None
    match error:
        case ApiResponseError():
            error_type = error.error_type or error_type
            message = hosted_refusal_message(error=error)
            next_step = hosted_refusal_next_step(error=error)
            error_domain = error.error_domain
            retryable = error.retryable
        case RunFailedError():
            report = error.error
            error_domain = ErrorDomain.RUNTIME
            if report is not None:
                error_type = report.error_type or error_type
                error_domain = report.error_domain or error_domain
                retryable = report.retryable
            if report is not None and report.user_action is not None and report.user_action.detail:
                next_step = report.user_action.detail
            else:
                next_step = f"The run {error.run_id} ended {error.status}: change what the message names, then run again"
        case RunTimeoutError():
            error_domain = ErrorDomain.RUNTIME
            next_step = (
                f"The run {error.run_id} keeps running on the hosted API: find it on app.pipelex.com, or read its result "
                "later with pipelex-sdk's PipelexAPIClient.wait_for_result"
            )
        case PipelineExecuteTimeoutError():
            error_domain = ErrorDomain.RUNTIME
            next_step = "The run outlived the hosted API's synchronous ceiling: run it again, it starts and polls the run instead"
        case ApiUnreachableError():
            error_domain = ErrorDomain.CONFIG
            next_step = f"Check the network connection. {HOSTED_BASE_URL_NEXT_STEP}"
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
        case InputPreparationError():
            error_domain = ErrorDomain.INPUT
            next_step = "Check the inputs against the pipe's signature (pipelex-agent inputs prints a template), then run again"
        case _:
            next_step = "Check the run request: the method, the pipe and the inputs"
    return HostedErrorView(error_type=error_type, message=message, next_step=next_step, error_domain=error_domain, retryable=retryable)
