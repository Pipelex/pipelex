"""A run on the hosted Pipelex API, mapped onto pipelex-sdk's `PipelexAPIClient`.

The request names the method one of three ways, as the hosted API takes them: a local bundle sent as its
`.mthds` contents, a published method's address (`method_ref`, resolved by the hosted runner), or a stored method's
catalog id (`method_id`, resolved by the platform). Local files named in the inputs are uploaded first
(`pipelex.hosted.hosted_inputs`), then the run is started and followed to its end, which outlives the hosted
gateway's 30-second ceiling on a synchronous request.

The lifecycle is the one the SDK's `start_and_wait` drives, taken step by step so that the run's id is in hand once
the hosted API acknowledges the start: the caller is told it at once, and a failure while following the run names the
run, which may still be going and is paid for, instead of reading as a network failure before any run. A connection
lost after the request that runs the method was sent is not read as a network failure either, since the hosted API may
have created the run before it.
"""

from pathlib import Path
from typing import Any, Protocol, Self

import httpx
from mthds.protocol.exceptions import PipelineRequestError
from pipelex_sdk.client import PipelexAPIClient
from pipelex_sdk.crate_models import MthdsFileItem
from pipelex_sdk.errors import ApiUnreachableError, MissingMainStuffError, RunFailedError, RunLifecycleUnavailableError, RunTimeoutError
from pipelex_sdk.execute_result import results_from_execute
from pipelex_sdk.runs import RunResults
from pipelex_sdk.upload import UploadRecord
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from pipelex.hosted.exceptions import HostedRunOutcomeUnknownError, HostedRunPollingError
from pipelex.hosted.hosted_inputs import prepare_hosted_inputs

#: The `implementation` a bare runner names in its `GET /v1/version` handshake: an open-source pipelex-api, which
#: keeps no runs to poll. The same value pipelex-sdk's `start_and_wait` tests to choose the blocking route.
BARE_RUNNER_IMPLEMENTATION = "pipelex-api"
#: The transport failures httpx raises before a request leaves this machine: no connection was made, so no run exists.
#: Every other one (a read, a write, a protocol failure) may come after the hosted API received the request.
_PRE_SEND_TRANSPORT_ERRORS: tuple[type[httpx.TransportError], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.UnsupportedProtocol,
    httpx.ProxyError,
)


class RunStartedCallback(Protocol):
    """Told the id of the run the hosted API acknowledged, before the run is followed to its result."""

    def __call__(self, *, pipeline_run_id: str) -> None: ...


class HostedRunRequest(BaseModel):
    """One run to execute on the hosted API: its source, its pipe and its inputs.

    Exactly one source: `mthds_files` (a local bundle and the rest of its library), `method_ref` (an address such as
    `github.com/Pipelex/methods/documents@v0.1.7`) or `method_id` (a catalog id such as `mt_abc123`). Each file of
    `mthds_files` carries a label, its path: the signature read before the run sends it, so the hosted API names the
    file in the validation errors of a method that does not load, while the run itself takes the bare contents.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mthds_files: list[MthdsFileItem] | None = None
    method_ref: str | None = None
    method_id: str | None = None
    #: The pipe to run; `None` runs the method's entry pipe (a package manifest's or the bundle's `main_pipe`).
    pipe_code: str | None = None
    inputs: dict[str, Any] | None = None
    #: The directory a relative file path in the inputs resolves against: the inputs file's, `None` for inline inputs.
    inputs_base_dir: Path | None = None
    dynamic_output_concept_ref: str | None = None

    @model_validator(mode="after")
    def _exactly_one_source(self) -> Self:
        named = [name for name, value in (("mthds_files", self.mthds_files), ("method_ref", self.method_ref), ("method_id", self.method_id)) if value]
        if len(named) != 1:
            msg = f"A hosted run names exactly one source among mthds_files, method_ref and method_id, got {named or 'none'}"
            raise ValueError(msg)
        return self

    @property
    def mthds_contents(self) -> list[str] | None:
        if not self.mthds_files:
            return None
        return [mthds_file.content for mthds_file in self.mthds_files]


class HostedRunOutcome(BaseModel):
    """A completed hosted run: its results, the files uploaded for it, and the qualified pipe its inputs were read for."""

    model_config = ConfigDict(frozen=True)

    results: RunResults
    uploads: list[UploadRecord] = Field(default_factory=list[UploadRecord])
    #: The qualified ref (`domain.pipe_code`) of the pipe that ran, when the inputs' preparation read it; `None` otherwise.
    pipe_ref: str | None = None


async def _serves_run_lifecycle(*, client: PipelexAPIClient) -> bool:
    """Whether the server keeps runs to poll, decided as the SDK's `start_and_wait` decides it.

    The `GET /v1/version` handshake of a bare runner names it; any other answer, and a handshake that fails, is read
    as the hosted API, whose start then surfaces the real error.
    """
    try:
        version_info = await client.version()
    except (PipelineRequestError, httpx.HTTPError, ValidationError):
        return True
    implementation = (version_info.model_extra or {}).get("implementation")
    return not (isinstance(implementation, str) and implementation == BARE_RUNNER_IMPLEMENTATION)


async def _execute_blocking(*, client: PipelexAPIClient, request: HostedRunRequest, inputs: dict[str, Any] | None) -> RunResults:
    """The blocking `POST /v1/execute` of a server with no run store, lifted onto the results a started run returns."""
    result = await client.execute(
        pipe_code=request.pipe_code,
        mthds_contents=request.mthds_contents,
        inputs=inputs,
        dynamic_output_concept_ref=request.dynamic_output_concept_ref,
        method_ref=request.method_ref,
        method_id=request.method_id,
    )
    return results_from_execute(result)


async def _start_or_execute_unmapped(*, client: PipelexAPIClient, request: HostedRunRequest, inputs: dict[str, Any] | None) -> str | RunResults:
    if not await _serves_run_lifecycle(client=client):
        return await _execute_blocking(client=client, request=request, inputs=inputs)
    try:
        started = await client.start(
            pipe_code=request.pipe_code,
            mthds_contents=request.mthds_contents,
            inputs=inputs,
            dynamic_output_concept_ref=request.dynamic_output_concept_ref,
            method_ref=request.method_ref,
            method_id=request.method_id,
        )
    except RunLifecycleUnavailableError:
        return await _execute_blocking(client=client, request=request, inputs=inputs)
    return started.pipeline_run_id


async def _start_or_execute(*, client: PipelexAPIClient, request: HostedRunRequest, inputs: dict[str, Any] | None) -> str | RunResults:
    """Start the run and hand back its id; on a server that keeps no runs, run it on the blocking route and hand back its results.

    A start the server refuses for a missing run store created no run, so running the blocking route next cannot run
    the method twice.

    The SDK maps a transport failure to `ApiUnreachableError` on the routes it owns, but `start` and `execute`, which
    it inherits from mthds, let httpx's error through, and only some of them mean the hosted API was not reached. A
    failure before the request left this machine is mapped as the SDK maps it. Any later one, a connection lost after
    the request was sent, is a `HostedRunOutcomeUnknownError`: the hosted API may have created the run, and its id
    never arrived.
    """
    try:
        return await _start_or_execute_unmapped(client=client, request=request, inputs=inputs)
    except _PRE_SEND_TRANSPORT_ERRORS as exc:
        if isinstance(exc, httpx.TimeoutException):
            msg = f"Could not reach Pipelex API at {client.base_url} (timeout)"
            raise ApiUnreachableError(msg, api_url=client.base_url, code="ABORT_TIMEOUT") from exc
        code = type(exc).__name__
        msg = f"Could not reach Pipelex API at {client.base_url} ({code})"
        raise ApiUnreachableError(msg, api_url=client.base_url, code=code) from exc
    except httpx.TransportError as exc:
        msg = f"The connection to the hosted API at {client.base_url} failed after the run request was sent ({type(exc).__name__}: {exc})"
        raise HostedRunOutcomeUnknownError(msg) from exc


async def _follow(*, client: PipelexAPIClient, run_id: str) -> RunResults:
    """Poll a started run to its result.

    A failure that names the run already (a run that failed, one past the wait, one that delivered no main output) is
    raised as it is. Any other one met after the start was acknowledged, the network, the hosted API or an answer that
    does not parse, is raised as a `HostedRunPollingError` naming the run, which may still be going.
    """
    try:
        return await client.wait_for_result(run_id)
    except (RunFailedError, RunTimeoutError, MissingMainStuffError):
        raise
    except (PipelineRequestError, httpx.HTTPError, ValueError) as exc:
        # `ValueError` covers an answer that is not what the results route promises: a body that is not JSON
        # (`json.JSONDecodeError`) or one that drifted from the SDK's model (pydantic's `ValidationError`).
        msg = f"The run {run_id} started on the hosted API, but following it to its result failed: {exc}"
        raise HostedRunPollingError(msg, pipeline_run_id=run_id) from exc


async def run_hosted(*, client: PipelexAPIClient, request: HostedRunRequest, on_started: RunStartedCallback | None = None) -> HostedRunOutcome:
    """Run a method on the hosted API and wait for its result.

    Args:
        client: A started client, from `pipelex.hosted.client_factory.make_hosted_client`.
        request: The run.
        on_started: Told the run's id as soon as the hosted API acknowledges the start, before the run is followed, so
            a caller interrupted while waiting can still name the run. Not called on a server with no run store, whose
            blocking route answers with the results directly.

    Returns:
        The outcome, its `results` read the same way whatever the source: `results.main_stuff` is the main output's
        content, `results.working_memory` the whole working memory, `results.pipeline_run_id` the run's id.

    Raises:
        HostedLocalFileUploadUnavailableError: If the inputs name a local file and the method calls another one by its
            address, which the signature read cannot load.
        HostedMethodInvalidError: If the hosted API reads the method's signature and the method does not load.
        ApiResponseError: If the hosted API refuses the request: a key it does not accept, a method it cannot load
            (its `validation_errors` locate the fault), an input it rejects.
        RunFailedError: If the run started and ended in a status other than completed.
        RunTimeoutError: If the run outlived the wait; it keeps running, and its id resumes it.
        MissingMainStuffError: If the run completed and delivered no main output.
        HostedRunPollingError: If following a started run failed any other way; it names the run.
        HostedRunOutcomeUnknownError: If the connection failed after the run request was sent, so a run may exist.
        ApiUnreachableError: If the hosted API cannot be reached before the run request is sent.
        InputPreparationError: If a local file cannot be read or uploaded.
    """
    prepared = await prepare_hosted_inputs(
        client=client,
        mthds_files=request.mthds_files,
        method_ref=request.method_ref,
        method_id=request.method_id,
        pipe_code=request.pipe_code,
        inputs=request.inputs,
        inputs_base_dir=request.inputs_base_dir,
    )
    run_id_or_results = await _start_or_execute(client=client, request=request, inputs=prepared.inputs)

    if isinstance(run_id_or_results, RunResults):
        results = run_id_or_results
    else:
        if on_started is not None:
            on_started(pipeline_run_id=run_id_or_results)
        results = await _follow(client=client, run_id=run_id_or_results)
    return HostedRunOutcome(results=results, uploads=prepared.uploads, pipe_ref=prepared.pipe_ref)
