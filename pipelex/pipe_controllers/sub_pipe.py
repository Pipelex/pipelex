from typing import TYPE_CHECKING

from pydantic import BaseModel, field_validator

from pipelex.core.memory.exceptions import WorkingMemoryStuffNotFoundError, WorkingMemoryTypeError
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.inputs.exceptions import InputStuffSpecNotFoundError, PipeRunInputsError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.variable_multiplicity import PresenceMarker, VariableMultiplicity
from pipelex.core.stuffs.list_content import ListContent
from pipelex.interpreter_hub import get_pipe_router, get_required_pipe
from pipelex.pipe_controllers.batch.pipe_batch import PipeBatch
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import BatchParams, PipeRunParams, output_multiplicity_to_apply
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.misc.string_utils import get_root_from_dotted_path

if TYPE_CHECKING:
    from pipelex.libraries.library_crate import LibraryCrate


class SubPipe(BaseModel):
    pipe_code: str
    output_name: str | None = None
    output_multiplicity: VariableMultiplicity | None = None
    batch_params: BatchParams | None = None

    @field_validator("batch_params", mode="after")
    @classmethod
    def refuse_dotted_input_list(cls, batch_params: BatchParams | None) -> BatchParams | None:
        """Refuse a batch over a dotted path: the sequence holding the step rewrites a dotted `batch_over` into a binding step
        followed by a batch over the bound name, so a step only ever batches over a name in working memory.
        """
        if batch_params is not None and "." in batch_params.input_list_stuff_name:
            msg = (
                f"A step batches over the dotted path '{batch_params.input_list_stuff_name}': a step batches over a name in working memory, "
                "and the PipeSequence holding it binds a dotted `batch_over` to a name of its own first."
            )
            raise ValueError(msg)
        return batch_params

    def result_spec(self, *, step_pipe: PipeAbstract) -> StuffSpec:
        """The spec of what the step stores under its result, `step_pipe` being the pipe it runs, resolved as the run path resolves it.

        A batched step stores the list of its branches' results, a `PipeBatch` wrapping the pipe: `X[]` whatever the pipe
        outputs and whatever count the step asks for, since an absent branch result is dropped from the list, which is never
        absent. Any other step stores the pipe's output, its multiplicity overridden by the step's `nb_output` or
        `multiple_output`, and a single result keeps the pipe's presence.
        """
        if self.batch_params is not None:
            return StuffSpec(concept=step_pipe.output.concept, multiplicity=True)
        multiplicity_resolution = output_multiplicity_to_apply(
            base_multiplicity=step_pipe.output.multiplicity,
            override_multiplicity=self.output_multiplicity,
        )
        multiplicity: VariableMultiplicity | None
        if not multiplicity_resolution.is_multiple_outputs_enabled:
            multiplicity = None
        elif multiplicity_resolution.specific_output_count is not None:
            multiplicity = multiplicity_resolution.specific_output_count
        else:
            multiplicity = True
        presence = step_pipe.output.presence if multiplicity is None else PresenceMarker.PLAIN
        return StuffSpec(concept=step_pipe.output.concept, multiplicity=multiplicity, presence=presence)

    async def run_pipe(
        self,
        *,
        calling_pipe_code: str,
        working_memory: WorkingMemory,
        job_metadata: JobMetadata,
        sub_pipe_run_params: PipeRunParams,
        library_crate: "LibraryCrate | None" = None,
    ) -> PipeOutput:
        # `is not None`, not truthiness: `False` (force single) and `0` are overrides a step can
        # carry, and dropping them here would let the run path inherit the caller's multiplicity
        # while `is_plural_step_result` — which hands this same value to the shared resolution —
        # promised the step's own answer.
        if self.output_multiplicity is not None:
            sub_pipe_run_params.output_multiplicity = self.output_multiplicity

        sub_pipe = get_required_pipe(pipe_code=self.pipe_code)

        # Case 1: Batch processing
        if batch_params := self.batch_params:
            sub_pipe_run_params.batch_params = batch_params

            # The list is named as its author wrote it: a dotted `batch_over` is stored under a private name, which the messages of
            # the working memory's own errors would name, so neither is quoted here.
            list_label = batch_params.input_list_label
            try:
                working_memory.get_typed_object_or_attribute(name=batch_params.input_list_stuff_name, wanted_type=ListContent)
            except WorkingMemoryStuffNotFoundError as exc:
                msg = (
                    f"The list '{list_label}' that the step running pipe '{self.pipe_code}' of pipe '{calling_pipe_code}' batches over "
                    "is not in working memory."
                )
                raise PipeRunInputsError(
                    message=msg,
                    run_mode=sub_pipe_run_params.run_mode,
                    pipe_code=self.pipe_code,
                    variable_name=list_label,
                    concept_code=None,
                ) from exc
            except WorkingMemoryTypeError as exc:
                msg = (
                    f"The value '{list_label}' that the step running pipe '{self.pipe_code}' of pipe '{calling_pipe_code}' batches over "
                    "is not a list: a batch runs its pipe once per item of a list."
                )
                raise PipeRunInputsError(
                    message=msg,
                    run_mode=sub_pipe_run_params.run_mode,
                    pipe_code=self.pipe_code,
                    variable_name=list_label,
                    concept_code=None,
                ) from exc

            try:
                item_stuff_spec = sub_pipe.inputs.get_required_stuff_spec(variable_name=batch_params.input_item_stuff_name)
            except InputStuffSpecNotFoundError as exc:
                msg = (
                    f"Batch input item named '{batch_params.input_item_stuff_name}' from '{calling_pipe_code}' is not "
                    f"in SubPipe '{self.pipe_code}' input stuff specs: {sub_pipe.inputs}"
                )
                raise PipeRunInputsError(
                    message=msg,
                    run_mode=sub_pipe_run_params.run_mode,
                    pipe_code=self.pipe_code,
                    variable_name=batch_params.input_item_stuff_name,
                    concept_code=None,
                ) from exc
            # The batch is built as the runtime pipe, not from a blueprint: its list is a name of the calling sequence's memory,
            # a private one for a dotted `batch_over` the sequence rewrote, or any name a step stores under, never an input
            # name an author declares, so the input-name grammar a blueprint enforces does not apply to it.
            pipe_batch = PipeBatch(
                domain_code=sub_pipe.domain_code,
                # Derived from the resolved pipe's LOCAL code, not from `self.pipe_code` — that is a qualified ref
                # (`domain.foo`), and suffixing it would name `domain.foo_batch` while the domain is added a second time.
                code=f"{sub_pipe.code}_batch",
                description=f"Batch processing for {self.pipe_code}",
                inputs=InputStuffSpecs(root={batch_params.input_list_stuff_name: StuffSpec(concept=item_stuff_spec.concept)}),
                output=StuffSpec(concept=sub_pipe.output.concept),
                branch_pipe_code=self.pipe_code,
                batch_params=batch_params,
            )
            pipe_output = await get_pipe_router().run(
                pipe_job=PipeJobFactory.make_pipe_job(
                    pipe=pipe_batch,
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                    pipe_run_params=sub_pipe_run_params,
                    output_name=self.output_name,
                    library_crate=library_crate,
                ),
            )
        # Case 2: Condition processing
        elif isinstance(sub_pipe, PipeCondition):
            pipe_output = await get_pipe_router().run(
                pipe_job=PipeJobFactory.make_pipe_job(
                    pipe=sub_pipe,
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                    pipe_run_params=sub_pipe_run_params,
                    output_name=self.output_name,
                    library_crate=library_crate,
                ),
            )
        else:
            # Case 3: Normal processing
            required_variables = sub_pipe.required_variables()
            # Extract root names from full paths for looking up stuffs in working memory
            # TODO: Merge `needed_inputs` and `required_variables` methods for cleaner code.
            required_stuff_names: set[str] = set()
            for req_var in required_variables:
                if req_var.startswith("_"):
                    continue
                root_name = get_root_from_dotted_path(req_var)
                # A variable declared optional (`?`) on the sub-pipe is never presence-required
                # (the `@?` fix, D7): the pipe runs with the slot absent and its guarded
                # templates handle it.
                declared_spec = sub_pipe.inputs.root.get(root_name)
                if declared_spec is not None and declared_spec.presence.is_optional:
                    continue
                required_stuff_names.add(root_name)
            # A recorded absence is not a miss: the sub-pipe's own gate applies the trichotomy
            # (skip / run / force). Only a name with neither a value nor a record is a hard miss.
            missing_names = working_memory.list_missing_names(names=required_stuff_names)
            if missing_names:
                sub_pipe_path = [*sub_pipe_run_params.pipe_stack, self.pipe_code]
                sub_pipe_path_str = ".".join(sub_pipe_path)
                error_details = f"SubPipe '{sub_pipe_path_str}', required_variables: {required_variables}, missing: '{missing_names[0]}'"
                msg = f"Some required stuff(s) not found: {error_details}"
                raise PipeRunInputsError(
                    message=msg,
                    run_mode=sub_pipe_run_params.run_mode,
                    pipe_code=self.pipe_code,
                    variable_name=missing_names[0],
                    concept_code=None,
                )
            pipe_output = await get_pipe_router().run(
                pipe_job=PipeJobFactory.make_pipe_job(
                    pipe=sub_pipe,
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                    pipe_run_params=sub_pipe_run_params,
                    output_name=self.output_name,
                    library_crate=library_crate,
                ),
            )

        return pipe_output
