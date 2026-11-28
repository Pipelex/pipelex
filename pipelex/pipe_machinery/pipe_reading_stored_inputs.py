"""The base of every pipe that runs: the one place the input gate's stored values are loaded.

`PipeAbstract.ensure_inputs_honour_their_contracts` reads the real value of each constrained input, so it loads the
stored ones first through `_load_stored_input_values`. Loading reaches `pipelex.kernel.stored_value_ops`, which
`pipe_abstract` cannot import: the loader's chain (`runtime_hub`, `orchestrator_registry`, `pipe_job`) comes back to
`pipe_abstract`, a cycle pyright reports even for a deferred import. This module sits above both, and `PipeOperator`,
`PipeController` and `PipeSignature` derive from it, so they share one implementation; a pipe class deriving from
`PipeAbstract` directly keeps the base's body, which loads nothing, and the gate refuses a stored value it cannot read.
"""

from typing import Any

from typing_extensions import override

from pipelex.kernel.stored_value_ops import load_stored_values_through_leaf
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata


class PipeReadingStoredInputs(PipeAbstract):
    """A pipe whose input gate loads the stored values it checks, through the content generator's leaf."""

    @override
    async def _load_stored_input_values(self, *, roots: dict[str, Any], job_metadata: JobMetadata, pipe_run_params: PipeRunParams) -> None:
        await load_stored_values_through_leaf(
            roots=roots, read_paths=None, job_metadata=job_metadata, cogt_run_params=pipe_run_params.cogt_run_params
        )
