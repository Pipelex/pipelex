from typing_extensions import override

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.input_requirements_factory import InputRequirementsFactory
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.hub import get_required_concept
from pipelex.pipe_controllers.batch.pipe_batch import PipeBatch
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_run.pipe_run_params import BatchParams


class PipeBatchFactory(PipeFactoryProtocol[PipeBatchBlueprint, PipeBatch]):
    @classmethod
    @override
    def make_from_blueprint(
        cls,
        domain: str,
        pipe_code: str,
        blueprint: PipeBatchBlueprint,
        concept_codes_from_the_same_domain: list[str] | None = None,
    ) -> PipeBatch:
        output_domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_code(
            domain=domain,
            concept_string_or_code=blueprint.output,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
        return PipeBatch(
            domain=domain,
            code=pipe_code,
            description=blueprint.description,
            inputs=InputRequirementsFactory.make_from_blueprint(
                domain=domain,
                blueprint=blueprint.inputs or {},
                concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
            ),
            output=get_required_concept(
                concept_string=ConceptFactory.make_concept_string_with_domain(
                    domain=output_domain_and_code.domain,
                    concept_code=output_domain_and_code.concept_code,
                ),
            ),
            branch_pipe_code=blueprint.branch_pipe_code,
            batch_params=BatchParams.make_optional_batch_params(
                input_list_name=blueprint.input_list_name,
                input_item_name=blueprint.input_item_name,
            ),
        )
