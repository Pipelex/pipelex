"""A run on the hosted Pipelex API, mapped onto pipelex-sdk's `PipelexAPIClient`.

The request names the method one of three ways, as the hosted API takes them: a local method sent as its tree, the
MTHDS protocol's `files` map, a published method's address (`method_ref`, resolved by the hosted runner), or a stored
method's catalog id (`method_id`, resolved by the platform). A local method's tree is handed to the SDK as `contents`,
each bundle's bytes by tree path, for both the signature read and the run, and the SDK sends it as `mthds` prepares
it: inline when its map weighs 256 KiB or less, otherwise every file by hash once the blobs the hosted API lacks are
uploaded, a file uploaded for the signature read being found held for the run. Local files named in the inputs are uploaded first
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
from pipelex_sdk.errors import ApiUnreachableError, MissingMainStuffError, RunFailedError, RunLifecycleUnavailableError, RunTimeoutError
from pipelex_sdk.execute_result import results_from_execute
from pipelex_sdk.runs import RunResults
from pipelex_sdk.upload import UploadRecord
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from pipelex.hosted.exceptions import HostedRunOutcomeUnknownError, HostedRunPollingError
from pipelex.hosted.hosted_inputs import prepare_hosted_inputs
from pipelex.system.usage_stats.usage_stats_client import note_command_hosted

#: The `implementation` a bare runner names in its `GET /v1/version` handshake: an open-source pipelex-api, which
#: keeps no runs to poll. The same value pipelex-sdk's `start_and_wait` tests to choose the blocking route.
BARE_RUNNER_IMPLEMENTATION = "pipelex-api"


class RunStartedCallback(Protocol):
    """Told the id of the run the hosted API acknowledged, before the run is followed to its result."""

    def __call__(self, *, pipeline_run_id: str) -> None: ...


class HostedRunRequest(BaseModel):
    """One run to execute on the hosted API: its source, its pipe and its inputs.

    Exactly one source: `contents` (a local method's bundles, with the rest of its library, as one tree's bytes by tree
    path), `method_ref` (an address such as `github.com/Pipelex/methods/documents@v0.1.7`) or `method_id` (a catalog id
    such as `mt_abc123`). The tree path a bundle is keyed by is how the hosted API names it, in the validation errors of
    a method that does not load and in the run's own diagnostics.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    contents: dict[str, bytes] | None = None
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
        named = [name for name, value in (("contents", self.contents), ("method_ref", self.method_ref), ("method_id", self.method_id)) if value]
        if len(named) != 1:
            msg = f"A hosted run names exactly one source among contents, method_ref and method_id, got {named or 'none'}"
            raise ValueError(msg)
        return self


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
        contents=request.contents,
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
            contents=request.contents,
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

    The SDK raises `ApiUnreachableError` for every transport failure, chained from httpx's error, and decides whether
    a run may have started (`run_may_have_started`): only on the start or the execute request itself, and only when the
    failure does not prove the request never left this machine. A failure it reads as starting nothing stays the SDK's
    error: the version handshake, the blob requests of a tree sent by hash, or a connection that was never made. Any
    other one, a connection lost or a read timed out once the run request may have left, is a
    `HostedRunOutcomeUnknownError`: the hosted API may have created the run, and its id never arrived.
    """
    try:
        return await _start_or_execute_unmapped(client=client, request=request, inputs=inputs)
    except ApiUnreachableError as exc:
        if not exc.run_may_have_started:
            raise
        transport_error = exc.__cause__
        failure = f"{type(transport_error).__name__}: {transport_error}" if transport_error is not None else str(exc)
        msg = f"The connection to the hosted API at {client.base_url} failed on the run request, which the hosted API may have received ({failure})"
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
        # The SDK raises a `PipelineRequestError` for the network and for an answer it cannot read; httpx's errors and
        # `ValueError` (a body that is not JSON, one that drifted from the SDK's model) are caught too, so that no
        # failure met after the start was acknowledged loses the id of a run that may still be going.
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
        HostedRunOutcomeUnknownError: If the connection failed on the run request in a way that may have let it reach
            the hosted API, so a run may exist.
        ApiUnreachableError: If a request got no answer and pipelex-sdk reads it as starting no run.
        InputPreparationError: If a local file cannot be read or uploaded.
        MethodFileTransferError: If a file of the method's tree the hosted API lacks could not be uploaded, so no run
            started.
    """
    # A command running this sends its work to the hosted API; its `command_completed` says so and no more.
    note_command_hosted()
    prepared = await prepare_hosted_inputs(
        client=client,
        contents=request.contents,
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
