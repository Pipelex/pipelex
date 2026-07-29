from typing import Literal

from typing_extensions import override

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint


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
