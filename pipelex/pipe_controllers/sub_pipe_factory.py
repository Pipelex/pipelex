from pipelex.core.pipes.variable_multiplicity import make_variable_multiplicity
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_run.pipe_run_params import BatchParams


class SubPipeFactory:
    @classmethod
    def make_from_blueprint(
        cls,
        blueprint: SubPipeBlueprint,
        concept_codes_from_the_same_domain: list[str] | None = None,
    ) -> SubPipe:
        """Create a SubPipe from a SubPipeBlueprint."""
        output_multiplicity = make_variable_multiplicity(
            nb_items=blueprint.nb_output,
            multiple_items=blueprint.multiple_output,
        )
        batch_params: BatchParams | None = None
        if blueprint.batch_over and blueprint.batch_as:
            batch_params = BatchParams.make_batch_params(
                input_list_name=blueprint.batch_over,
                input_item_name=blueprint.batch_as,
            )
        else:
            batch_params = None
        return SubPipe(
            pipe_code=blueprint.pipe,
            output_name=blueprint.result,
            output_multiplicity=output_multiplicity,
            batch_params=batch_params,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
