from typing import Any, ClassVar

from mthds.protocol.problem.registry import CoreCode
from pipelex_sdk.validation_models import ValidationErrorItem
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration, ErrorCodeSet


class HostedRunError(PipelexError):
    """Base class for errors pipelex raises itself while running a method on the hosted Pipelex API.

    An error the hosted API answers, or one the pipelex-sdk client raises on the way, keeps the SDK's own class
    (`ApiResponseError`, `ApiUnreachableError`, `RunFailedError`, …); these are the ones pipelex detects itself: before
    it sends anything, from the verdict of the method's signature, from a connection lost after the run request was
    sent, while following a run it started, or when the run is interrupted on this machine. Most are the client's own
    findings, so they carry the `client.` codes, which no response is the body of.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR


class HostedBaseUrlError(HostedRunError):
    """The base URL of the hosted API is not an origin: it carries a path, a query, credentials, or a scheme other than http or https.

    The message names where the value came from, `--base-url` or `PIPELEX_BASE_URL`, and what an origin looks like.
    """

    error_code = CoreCode.CLIENT_NOT_CONFIGURED
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Give the hosted API's origin as scheme://host[:port], such as https://api.pipelex.com, in --base-url or PIPELEX_BASE_URL",
    )


class HostedRunSourceError(HostedRunError):
    """A hosted run cannot be given its method: no bundle file, an unreadable method file, no `.mthds` file, or `-L` with an address or a catalog id.

    The hosted API resolves a published address or a catalog id itself and loads no local library, so `-L` is refused
    with either. Every other case is about the files a hosted run sends: none named, none found in the library
    directories, or one that cannot be read.
    """

    error_code = CoreCode.CLIENT_ARGUMENT_INVALID


class HostedMethodInvalidError(HostedRunError):
    """The hosted API read the method's signature before the run and found that the method does not load.

    Raised from `POST /v1/pipe-io`'s invalid verdict, before any run starts. Its `validation_errors` are the hosted
    API's items, each naming the file it found the fault in by its tree path in the tree the run sends.
    """

    error_code = CoreCode.METHOD_INVALID
    user_action = UserAction(kind=UserActionKind.CHANGE_INPUT, detail="Fix the method as each validation error says, then run it again")

    def __init__(self, message: str, *, validation_errors: list[ValidationErrorItem]):
        super().__init__(message)
        self.validation_errors = validation_errors


class HostedRunPollingError(HostedRunError):
    """A run started on the hosted API, but following it to its result failed: the network, the hosted API, or its answer.

    The run was acknowledged, so it may still be running, and it is paid for: `pipeline_run_id` locates it, and running
    the command again would start another one. The cause is the failure met while following it.
    """

    error_code = CoreCode.CLIENT_FOLLOW_FAILED

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

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"pipeline_run_id": self.pipeline_run_id}


class HostedRunOutcomeUnknownError(HostedRunError):
    """The request that runs the method may have reached the hosted API, and the connection failed before its answer came back.

    The hosted API may have created the run before the connection failed, with no way to tell from here: its id never
    arrived. Running the command again could start a second paid run, so the next step is the run history first. The
    cause is pipelex-sdk's `ApiUnreachableError` for the start or the execute request, which the SDK reads as one that
    may have started the run (`run_may_have_started`); its own cause is the transport failure, such as a read, a write,
    a protocol failure or a body that could not be decoded, which does not prove the request never left this machine.
    """

    error_code = CoreCode.CLIENT_OUTCOME_UNKNOWN
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
    start request may still have reached the hosted API. The code follows: following a started run stopped
    (`client.follow_failed`) once a run id arrived, a call that may have created a run (`client.outcome_unknown`)
    before one did.
    """

    error_code = ErrorCodeSet(default=CoreCode.CLIENT_OUTCOME_UNKNOWN, others=(CoreCode.CLIENT_FOLLOW_FAILED,))

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
        if pipeline_run_id is not None:
            self.with_error_code(CoreCode.CLIENT_FOLLOW_FAILED)

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"pipeline_run_id": self.pipeline_run_id}


class HostedLocalFileUploadUnavailableError(HostedRunError):
    """A hosted run's inputs name a local file, and its method calls another method by its address.

    Uploading a local file is guided by the pipe's signature, which `POST /v1/pipe-io` reads with only the packages the
    request ships, and a hosted run ships none, while the run route fetches such a dependency. The method is not at
    fault: the same run goes through when the file is given as an https URL, which needs no upload.
    """

    error_code = CoreCode.REQUEST_UNSUPPORTED
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Pass each local file as an https URL the hosted API can fetch, instead of a path on this machine, then run again",
    )
