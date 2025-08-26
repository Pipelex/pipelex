from typing import List, Optional

from pipelex.core.pipes.pipe_run_params import BatchParams, make_output_multiplicity
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class SubPipeFactory:
    @classmethod
    def make_from_blueprint(
        cls,
        blueprint: SubPipeBlueprint,
        concept_codes_from_the_same_domain: Optional[List[str]] = None,
    ) -> SubPipe:
        """Create a SubPipe from a SubPipeBlueprint."""
        output_multiplicity = make_output_multiplicity(
            nb_output=blueprint.nb_output,
            multiple_output=blueprint.multiple_output,
        )
        batch_params = BatchParams.make_optional_batch_params(
            input_list_name=blueprint.batch_over,
            input_item_name=blueprint.batch_as,
        )
        return SubPipe(
            pipe_code=blueprint.pipe,
            output_name=blueprint.result,
            output_multiplicity=output_multiplicity,
            batch_params=batch_params,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
