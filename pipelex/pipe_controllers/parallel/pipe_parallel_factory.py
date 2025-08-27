from typing import List, Optional

from typing_extensions import override

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.pipe_input_spec_factory import PipeInputSpecFactory
from pipelex.exceptions import PipeDefinitionError
from pipelex.hub import get_concept_provider
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeFactory


class PipeParallelFactory(PipeFactoryProtocol[PipeParallelBlueprint, PipeParallel]):
    @classmethod
    @override
    def make_from_blueprint(
        cls,
        domain: str,
        pipe_code: str,
        blueprint: PipeParallelBlueprint,
        concept_codes_from_the_same_domain: Optional[List[str]] = None,
    ) -> PipeParallel:
        parallel_sub_pipes: List[SubPipe] = []
        for sub_pipe_blueprint in blueprint.parallels:
            if not sub_pipe_blueprint.result:
                raise PipeDefinitionError("PipeParallel requires a result specified for each parallel sub pipe")
            sub_pipe = SubPipeFactory.make_from_blueprint(sub_pipe_blueprint, concept_codes_from_the_same_domain=concept_codes_from_the_same_domain)
            parallel_sub_pipes.append(sub_pipe)
        if not blueprint.add_each_output and not blueprint.combined_output:
            raise PipeDefinitionError("PipeParallel requires either add_each_output or combined_output to be set")

        if blueprint.combined_output:
            combined_output_domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_concept_code(
                domain=domain,
                concept_string_or_concept_code=blueprint.output_concept_string_or_concept_code,
                concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
            )
            combined_output = get_concept_provider().get_required_concept(
                concept_string=ConceptFactory.construct_concept_string_with_domain(
                    domain=combined_output_domain_and_code.domain, concept_code=combined_output_domain_and_code.concept_code
                )
            )
        else:
            combined_output = None

        output_domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_concept_code(
            domain=domain,
            concept_string_or_concept_code=blueprint.output_concept_string_or_concept_code,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
        return PipeParallel(
            domain=domain,
            code=pipe_code,
            definition=blueprint.definition,
            inputs=PipeInputSpecFactory.make_from_blueprint(
                domain=domain, blueprint=blueprint.inputs or {}, concept_codes_from_the_same_domain=concept_codes_from_the_same_domain
            ),
            output=get_concept_provider().get_required_concept(
                concept_string=ConceptFactory.construct_concept_string_with_domain(
                    domain=output_domain_and_code.domain, concept_code=output_domain_and_code.concept_code
                )
            ),
            parallel_sub_pipes=parallel_sub_pipes,
            add_each_output=blueprint.add_each_output,
            combined_output=combined_output,
        )
