from typing import Any, Literal, cast

from pydantic import field_validator
from typing_extensions import override

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.pipe_controllers.binding.binding_step_blueprint import BINDING_FROM_KEY, is_binding_step_dict, raw_step_mapping
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint, is_dotted_batch_over
from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint
from pipelex.validation_error_types import PipeValidationErrorType


class PipeParallelBlueprint(PipeBlueprint):
    type: Literal["PipeParallel"] = "PipeParallel"
    pipe_category: Literal["PipeController"] = "PipeController"
    branches: list[SubPipeBlueprint]
    add_each_output: bool = False

    @property
    @override
    def pipe_dependencies(self) -> set[str]:
        """Return the set of pipe codes from the parallel branches."""
        return {branch.pipe for branch in self.branches}

    @field_validator("branches", mode="before")
    @classmethod
    def refuse_binding_branches(cls, branches: Any) -> Any:
        """Refuse a branch that binds: a branch written as a binding step, or a branch whose `batch_over` is a dotted path.

        A binding orders a value before the steps that read it, and branches run concurrently, so a binding
        among them would only be a binding before the parallel, written in the wrong place. A dotted
        `batch_over` is a binding followed by a batch, so a branch carries only a plain one.
        """
        if not isinstance(branches, list):
            # Not a list at all: pydantic's own `list_type` error names the field and what it holds.
            return branches
        branch_list = cast("list[Any]", branches)
        for branch_index, branch in enumerate(branch_list):
            batch_over: Any
            if isinstance(branch, SubPipeBlueprint):
                batch_over = branch.batch_over
            else:
                raw_branch = raw_step_mapping(raw_step=branch)
                if raw_branch is None:
                    continue
                if is_binding_step_dict(raw_step=raw_branch):
                    from_path = raw_branch.get(BINDING_FROM_KEY)
                    msg = (
                        f"Branch {branch_index + 1} of the parallel is a binding step (it carries `from`), but a PipeParallel branch is always "
                        f"a pipe step: bind the value in a step of the calling PipeSequence, before the PipeParallel step "
                        f'(`{{ from = "{from_path}", result = "<name>" }}`), and have the branch read that name.'
                    )
                    raise PipeValidationError(message=msg, error_type=PipeValidationErrorType.BINDING_STEP_INVALID)
                batch_over = raw_branch.get("batch_over")
            if isinstance(batch_over, str) and is_dotted_batch_over(batch_over=batch_over):
                msg = (
                    f"Branch {branch_index + 1} of the parallel batches over the dotted path '{batch_over}', but a dotted `batch_over` binds "
                    "the list at its path before batching over it, and a PipeParallel branch never binds: bind the list in a step of the "
                    f'calling PipeSequence, before the PipeParallel step (`{{ from = "{batch_over}", result = "<name>" }}`), and have the '
                    'branch batch over that name (`batch_over = "<name>"`).'
                )
                raise PipeValidationError(message=msg, error_type=PipeValidationErrorType.BINDING_STEP_INVALID, variable_names=[batch_over])
        return branch_list

    @override
    def validate_output(self):
        """A parallel always combines its branch outputs into its declared output.

        The combination is a named composite, so the output must be `Composite` or a structured
        concept — never a scalar native concept, `Dynamic`, `Anything`, or a list (a list
        aggregation is PipeBatch's shape). The structured concept's field compatibility with the
        branch result names is checked later, at library validation time.
        """
        # generic_validate_output already checked the syntax, so this parse cannot fail
        output_parse_result = parse_concept_with_multiplicity(self.output)
        if output_parse_result.multiplicity is not None:
            msg = (
                f"PipeParallel output '{self.output}' must not declare a multiplicity: "
                "a parallel combination is a named composite, never a list (a list aggregation is PipeBatch's shape)."
            )
            raise ValueError(msg)
        concept_ref_or_code = output_parse_result.concept_ref_or_code
        if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=concept_ref_or_code):
            native_code = NativeConceptCode(concept_ref_or_code.split(".")[-1])
            if not native_code.is_composite:
                msg = (
                    f"PipeParallel output '{self.output}' is invalid: the output of a parallel must be 'Composite' "
                    "or a structured concept whose fields correspond to the branch result names."
                )
                raise ValueError(msg)
