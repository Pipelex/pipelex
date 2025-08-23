from typing import List, Literal, Optional

from typing_extensions import override

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.pipe_input_spec_factory import PipeInputSpecFactory
from pipelex.core.pipes.pipe_run_params import BatchParams
from pipelex.hub import get_concept_provider
from pipelex.pipe_controllers.pipe_batch import PipeBatch


class PipeBatchBlueprint(PipeBlueprint):
    type: Literal["PipeBatch"] = "PipeBatch"
    branch_pipe_code: str

    input_list_name: Optional[str] = None
    input_item_name: Optional[str] = None


class PipeBatchFactory(PipeFactoryProtocol[PipeBatchBlueprint, PipeBatch]):
    @classmethod
    @override
    def make_from_blueprint(
        cls,
        domain: str,
        pipe_code: str,
        pipe_blueprint: PipeBatchBlueprint,
        concept_codes_from_the_same_domain: Optional[List[str]] = None,
    ) -> PipeBatch:
        if pipe_blueprint.output == "ChannelSummary":
            from pipelex import pretty_print

            pretty_print(domain, title="domain")
            pretty_print(concept_codes_from_the_same_domain, title="concept_codes_fromdzdzq_the_same_domain")
            pretty_print(domain, title="domain")
        output_concept_domain, output_concept_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_concept_code(
            domain=domain,
            concept_string_or_concept_code=pipe_blueprint.output,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
        return PipeBatch(
            domain=domain,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            inputs=PipeInputSpecFactory.make_from_blueprint(
                domain=domain, blueprint=pipe_blueprint.inputs or {}, concept_codes_from_the_same_domain=concept_codes_from_the_same_domain
            ),
            output=get_concept_provider().get_required_concept(
                concept_string=ConceptFactory.construct_concept_string_with_domain(domain=output_concept_domain, concept_code=output_concept_code)
            ),
            branch_pipe_code=pipe_blueprint.branch_pipe_code,
            batch_params=BatchParams.make_optional_batch_params(
                input_list_name=pipe_blueprint.input_list_name or False,
                input_item_name=pipe_blueprint.input_item_name,
            ),
        )
