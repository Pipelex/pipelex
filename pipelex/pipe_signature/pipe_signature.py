from typing import TYPE_CHECKING, Literal

from typing_extensions import override

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_blueprint import PipeType
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipe_signature.exceptions import PipeSignatureNotExecutableError
from pipelex.pipeline.job_metadata import JobMetadata

if TYPE_CHECKING:
    from pipelex.libraries.library_crate import LibraryCrate


class PipeSignature(PipeAbstract):
    """Runtime stand-in for a contract-only `PipeSignatureSpec`.

    Dry-run mints a mock output via the declared `StuffSpec`. Live-run raises
    `PipeSignatureNotExecutableError` to enforce that signatures must be replaced with
    a real implementation before the pipeline ships.
    """

    type: Literal["PipeSignature"] = "PipeSignature"
    # A signature is outside the executable taxonomy: it has no `PipeCategory`. `type` stays the
    # discriminator tag; `pipe_category` is None (the base validator admits None only for signatures).
    pipe_category: None = None
    signature_for: PipeType | None = None

    @property
    @override
    def is_signature(self) -> bool:
        return True

    @override
    def validate_inputs_static(self) -> None:
        pass

    @override
    def validate_inputs_with_library(self) -> None:
        pass

    @override
    def validate_output_static(self) -> None:
        pass

    @override
    def validate_output_with_library(self) -> None:
        pass

    @override
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        return self.inputs

    @override
    def required_variables(self) -> set[str]:
        return set(self.inputs.variables)

    @override
    async def _validate_before_run(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> None:
        pass

    @override
    async def _validate_after_run(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> None:
        pass

    @override
    async def _live_run_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        library_crate: "LibraryCrate | None" = None,
    ) -> PipeOutput:
        raise PipeSignatureNotExecutableError(pipe_ref=self.pipe_ref)

    @override
    async def _dry_run_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        library_crate: "LibraryCrate | None" = None,
    ) -> PipeOutput:
        mock_name = output_name or self.code
        typed_named = WorkingMemoryFactory.convert_stuff_spec_to_typed_named(stuff_spec=self.output, name=mock_name)
        mock_stuff = WorkingMemoryFactory.make_mock_stuff(typed_named_stuff_spec=typed_named)
        working_memory.set_new_main_stuff(stuff=mock_stuff, name=mock_name)
        return PipeOutput(working_memory=working_memory, pipeline_run_id=job_metadata.pipeline_run_id)
