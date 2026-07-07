from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata


class SandboxRunRequest(BaseModel):
    """Everything a sandbox needs to run ONE PipeFunc, and nothing else.

    Carries the crate (which includes ``python_sources`` — the customer's .py to register in the
    box), the transported working memory (the function's inputs), and the identity of the pipe/
    function to run. Deliberately carries NO secrets: the box gets the customer's code + data only.
    """

    model_config = ConfigDict(extra="forbid")

    crate: LibraryCrate
    working_memory_raw: dict[str, Any]
    pipe_code: str
    function_name: str
    job_metadata: JobMetadata
    pipe_run_params: PipeRunParams


class SandboxRunResult(BaseModel):
    """What the sandbox returns: the output as a transported working memory (main stuff = the output).

    Transporting the output *through a working memory* (rather than as a bare StuffContent) is what
    preserves the dynamic-class identity on the way back — the receiver rebinds the class from the
    concept's ``structure_class_name`` against its own registry, exactly like the worker hydration.
    """

    model_config = ConfigDict(extra="forbid")

    output_memory_raw: dict[str, Any]
    function_module: str | None = None
    function_qualname: str | None = None


class SandboxClientProtocol(Protocol):
    """A place that can run a SandboxRunRequest and return its result.

    Implementations own the isolation boundary: a local subprocess for testing, a Daytona box in
    production. The executor above them is identical regardless.
    """

    async def run(self, *, request: SandboxRunRequest) -> SandboxRunResult: ...
