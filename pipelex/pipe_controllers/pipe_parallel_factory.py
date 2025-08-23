from typing import List, Literal, Optional

from pydantic import field_validator
from typing_extensions import override

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.pipe_input_spec_factory import PipeInputSpecFactory
from pipelex.exceptions import PipeDefinitionError
from pipelex.hub import get_concept_provider
from pipelex.pipe_controllers.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeBlueprint, SubPipeFactory


class PipeParallelBlueprint(PipeBlueprint):
    type: Literal["PipeParallel"] = "PipeParallel"
    parallels: List[SubPipeBlueprint]
    add_each_output: bool = True
    combined_output: Optional[str] = None

    @field_validator("combined_output", mode="before")
    def validate_combined_output(cls, combined_output: str) -> str:
        if combined_output:
            ConceptBlueprint.validate_concept_string_or_concept_code(concept_string_or_concept_code=combined_output)
        return combined_output


class PipeParallelFactory(PipeFactoryProtocol[PipeParallelBlueprint, PipeParallel]):
    @classmethod
    @override
    def make_from_blueprint(
        cls,
        domain: str,
        pipe_code: str,
        pipe_blueprint: PipeParallelBlueprint,
        concept_codes_from_the_same_domain: Optional[List[str]] = None,
    ) -> PipeParallel:
        parallel_sub_pipes: List[SubPipe] = []
        for sub_pipe_blueprint in pipe_blueprint.parallels:
            if not sub_pipe_blueprint.result:
                raise PipeDefinitionError("PipeParallel requires a result specified for each parallel sub pipe")
            sub_pipe = SubPipeFactory.make_from_blueprint(sub_pipe_blueprint, concept_codes_from_the_same_domain=concept_codes_from_the_same_domain)
            parallel_sub_pipes.append(sub_pipe)
        if not pipe_blueprint.add_each_output and not pipe_blueprint.combined_output:
            raise PipeDefinitionError("PipeParallel requires either add_each_output or combined_output to be set")

        if pipe_blueprint.combined_output:
            combined_output_domain, output_concept_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_concept_code(
                domain=domain,
                concept_string_or_concept_code=pipe_blueprint.output,
                concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
            )
            combined_output = get_concept_provider().get_required_concept(
                concept_string=ConceptFactory.construct_concept_string_with_domain(domain=combined_output_domain, concept_code=output_concept_code)
            )
        else:
            combined_output = None

        output_concept_domain, output_concept_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_concept_code(
            domain=domain,
            concept_string_or_concept_code=pipe_blueprint.output,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
        return PipeParallel(
            domain=domain,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            inputs=PipeInputSpecFactory.make_from_blueprint(
                domain=domain, blueprint=pipe_blueprint.inputs or {}, concept_codes_from_the_same_domain=concept_codes_from_the_same_domain
            ),
            output=get_concept_provider().get_required_concept(
                concept_string=ConceptFactory.construct_concept_string_with_domain(domain=output_concept_domain, concept_code=output_concept_code)
            ),
            parallel_sub_pipes=parallel_sub_pipes,
            add_each_output=pipe_blueprint.add_each_output,
            combined_output=combined_output,
        )
