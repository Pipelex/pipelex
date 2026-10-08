from typing import ClassVar

from pipelex_sdk.validation_models import ValidationErrorItem

from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind


class HostedRunError(PipelexError):
    """Base class for errors pipelex raises itself while running a method on the hosted Pipelex API.

    An error the hosted API answers, or one the pipelex-sdk client raises on the way, keeps the SDK's own class
    (`ApiResponseError`, `ApiUnreachableError`, `RunFailedError`, …); these are the ones pipelex detects itself: before
    it sends anything, from the verdict of the method's signature, from a connection lost after the run request was
    sent, while following a run it started, or when the run is interrupted on this machine.
    """

    _declared_title = "Hosted run error"


class HostedBaseUrlError(HostedRunError):
    """The base URL of the hosted API is not an origin: it carries a path, a query, credentials, or a scheme other than http or https.

    The message names where the value came from, `--base-url` or `PIPELEX_BASE_URL`, and what an origin looks like.
    """

    error_domain = ErrorDomain.INPUT
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Give the hosted API's origin as scheme://host[:port], such as https://api.pipelex.com, in --base-url or PIPELEX_BASE_URL",
    )
    _authors_caller_facing_message: ClassVar[bool] = True


class HostedRunSourceError(HostedRunError):
    """A hosted run cannot be given the method to run: no bundle file, no `.mthds` file in the library directories, or no source at all."""

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message: ClassVar[bool] = True


class HostedMethodInvalidError(HostedRunError):
    """The hosted API read the method's signature before the run and found that the method does not load.

    Raised from `POST /v1/pipe-io`'s invalid verdict, before any run starts. Its `validation_errors` are the hosted
    API's items, each naming the file it found the fault in by the label the file was sent under, which the run route
    could not do: it takes the method's files as bare contents.
    """

    error_domain = ErrorDomain.INPUT
    user_action = UserAction(kind=UserActionKind.CHANGE_INPUT, detail="Fix the method as each validation error says, then run it again")
    _authors_caller_facing_message: ClassVar[bool] = True

    def __init__(self, message: str, *, validation_errors: list[ValidationErrorItem]):
        super().__init__(message)
        self.validation_errors = validation_errors


class HostedRunPollingError(HostedRunError):
    """A run started on the hosted API, but following it to its result failed: the network, the hosted API, or its answer.

    The run was acknowledged, so it may still be running, and it is paid for: `pipeline_run_id` locates it, and running
    the command again would start another one. The cause is the failure met while following it.
    """

    error_domain = ErrorDomain.RUNTIME

    def __init__(self, message: str, *, pipeline_run_id: str):
        super().__init__(message)
        self.pipeline_run_id = pipeline_run_id
        self.user_action = UserAction(
            kind=UserActionKind.UNKNOWN,
            detail=(
                f"The run {pipeline_run_id} may still be running on the hosted API, and running the command again starts a new, paid "
                f"run: look the run up by its id on app.pipelex.com, or read its result with pipelex-sdk's "
                f"PipelexAPIClient.wait_for_result('{pipeline_run_id}')"
            ),
        )


class HostedRunOutcomeUnknownError(HostedRunError):
    """The request that runs the method was sent, and the connection failed before its answer came back.

    The hosted API may have created the run before the connection failed, with no way to tell from here: its id never
    arrived. Running the command again could start a second paid run, so the next step is the run history first. The
    cause is the transport failure, a read, a write or a protocol failure met after the request left this machine.
    """

    error_domain = ErrorDomain.RUNTIME
    user_action = UserAction(
        kind=UserActionKind.UNKNOWN,
        detail=(
            "A run may have started on the hosted API before the connection failed: check the run history on app.pipelex.com "
            "before running again, since running again starts a new, paid run"
        ),
    )


class HostedRunInterruptedError(HostedRunError):
    """The hosted run was interrupted on this machine, by Ctrl-C or a cancellation, while it was being started or followed.

    Interrupting stops the wait, not the run: a run the hosted API acknowledged keeps going and is paid for, and
    `pipeline_run_id` finds it again. Interrupted before the acknowledgement, `pipeline_run_id` is `None`, and the
    start request may still have reached the hosted API.
    """

    error_domain = ErrorDomain.RUNTIME
    _authors_caller_facing_message: ClassVar[bool] = True

    def __init__(self, *, pipeline_run_id: str | None):
        if pipeline_run_id is None:
            message = "Interrupted before the hosted API acknowledged a run"
            detail = (
                "If the start request had reached the hosted API, a run may have started: check the run history on app.pipelex.com "
                "before running again"
            )
        else:
            message = f"Interrupted while following the run {pipeline_run_id}, which keeps going on the hosted API"
            detail = (
                f"The run {pipeline_run_id} keeps going on the hosted API and is paid for: look it up by its id on app.pipelex.com, "
                f"or read its result with pipelex-sdk's PipelexAPIClient.wait_for_result('{pipeline_run_id}'); running the command "
                "again starts a new run"
            )
        super().__init__(message)
        self.pipeline_run_id = pipeline_run_id
        self.user_action = UserAction(kind=UserActionKind.UNKNOWN, detail=detail)


class HostedLocalFileUploadUnavailableError(HostedRunError):
    """A hosted run's inputs name a local file, and its method calls another method by its address.

    Uploading a local file is guided by the pipe's signature, which `POST /v1/pipe-io` reads, and the crate core behind
    that route loads no address-based dependency, while the run route fetches it. The method is not at fault: the same
    run goes through when the file is given as an https URL, which needs no upload.
    """

    error_domain = ErrorDomain.INPUT
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Pass each local file as an https URL the hosted API can fetch, instead of a path on this machine, then run again",
    )
    _authors_caller_facing_message: ClassVar[bool] = True
