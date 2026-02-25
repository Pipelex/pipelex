from typing import TYPE_CHECKING

from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_run.pipe_run_params import BatchParams

if TYPE_CHECKING:
    from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity


class SubPipeFactory:
    @classmethod
    def make_from_blueprint(
        cls,
        blueprint: SubPipeBlueprint,
    ) -> SubPipe:
        """Create a SubPipe from a SubPipeBlueprint."""
        batch_params: BatchParams | None = None
        output_multiplicity: VariableMultiplicity | None = None

        if blueprint.batch_over and blueprint.batch_as:
            batch_params = BatchParams.make_batch_params(
                input_list_name=blueprint.batch_over,
                input_item_name=blueprint.batch_as,
            )
            output_multiplicity = True
            if blueprint.nb_output:
                output_multiplicity = blueprint.nb_output
            elif blueprint.multiple_output:
                output_multiplicity = True
        elif blueprint.nb_output:
            output_multiplicity = blueprint.nb_output
        elif blueprint.multiple_output:
            output_multiplicity = True
        else:
            batch_params = None

        return SubPipe(
            pipe_code=blueprint.pipe,
            output_name=blueprint.result,
            output_multiplicity=output_multiplicity,
            batch_params=batch_params,
        )
