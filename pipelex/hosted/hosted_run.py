"""A run on the hosted Pipelex API, mapped onto pipelex-sdk's `PipelexAPIClient`.

The request names the method one of three ways, as the hosted API takes them: a local bundle sent as its
`.mthds` contents, a published method's address (`method_ref`, resolved by the hosted runner), or a stored method's
catalog id (`method_id`, resolved by the platform). Local files named in the inputs are uploaded first
(`pipelex.hosted.hosted_inputs`), then `start_and_wait` starts the run and polls it to its end, which outlives the
hosted gateway's 30-second ceiling on a synchronous request.
"""

from pathlib import Path
from typing import Any, Self

import httpx
from pipelex_sdk.client import PipelexAPIClient
from pipelex_sdk.crate_models import MthdsFileItem
from pipelex_sdk.errors import ApiUnreachableError
from pipelex_sdk.runs import RunResults
from pipelex_sdk.upload import UploadRecord
from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipelex.hosted.hosted_inputs import prepare_hosted_inputs


class HostedRunRequest(BaseModel):
    """One run to execute on the hosted API: its source, its pipe and its inputs.

    Exactly one source: `mthds_files` (a local bundle and the rest of its library, each file with an optional
    provenance label the hosted API threads into its diagnostics), `method_ref` (an address such as
    `github.com/Pipelex/methods/documents@v0.1.7`) or `method_id` (a catalog id such as `mt_abc123`).
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


async def run_hosted(*, client: PipelexAPIClient, request: HostedRunRequest) -> HostedRunOutcome:
    """Run a method on the hosted API and wait for its result.

    Args:
        client: A started client, from `pipelex.hosted.client_factory.make_hosted_client`.
        request: The run.

    Returns:
        The outcome, its `results` read the same way whatever the source: `results.main_stuff` is the main output's
        content, `results.working_memory` the whole working memory, `results.pipeline_run_id` the run's id.

    Raises:
        ApiResponseError: If the hosted API refuses the request: a key it does not accept, a method it cannot load
            (its `validation_errors` locate the fault), an input it rejects.
        RunFailedError: If the run started and ended in a status other than completed.
        RunTimeoutError: If the run outlived the wait; it keeps running, and its id resumes it.
        ApiUnreachableError: If the hosted API cannot be reached, whichever route the failure met.
        InputPreparationError: If a local file cannot be read or uploaded.
    """
    # The SDK maps a transport failure to `ApiUnreachableError` on the routes it owns, but the protocol routes it
    # inherits from mthds (`start` among them) let httpx's error through. It is mapped here the same way, so every
    # failure of a hosted run reaches the CLIs as one of the SDK's typed errors.
    try:
        prepared = await prepare_hosted_inputs(
            client=client,
            mthds_files=request.mthds_files,
            method_ref=request.method_ref,
            method_id=request.method_id,
            pipe_code=request.pipe_code,
            inputs=request.inputs,
            inputs_base_dir=request.inputs_base_dir,
        )
        results = await client.start_and_wait(
            pipe_code=request.pipe_code,
            mthds_contents=request.mthds_contents,
            inputs=prepared.inputs,
            dynamic_output_concept_ref=request.dynamic_output_concept_ref,
            method_ref=request.method_ref,
            method_id=request.method_id,
        )
    except httpx.TimeoutException as exc:
        msg = f"Could not reach Pipelex API at {client.base_url} (timeout)"
        raise ApiUnreachableError(msg, api_url=client.base_url, code="ABORT_TIMEOUT") from exc
    except httpx.TransportError as exc:
        code = type(exc).__name__
        msg = f"Could not reach Pipelex API at {client.base_url} ({code})"
        raise ApiUnreachableError(msg, api_url=client.base_url, code=code) from exc
    return HostedRunOutcome(results=results, uploads=prepared.uploads, pipe_ref=prepared.pipe_ref)
