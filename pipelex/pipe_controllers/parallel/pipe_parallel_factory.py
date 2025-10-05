from typing import TYPE_CHECKING

from typing_extensions import override

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.input_requirements_factory import InputRequirementsFactory
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.exceptions import PipeDefinitionError
from pipelex.hub import get_required_concept
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeFactory

if TYPE_CHECKING:
    from pipelex.pipe_controllers.sub_pipe import SubPipe


class PipeParallelFactory(PipeFactoryProtocol[PipeParallelBlueprint, PipeParallel]):
    @classmethod
    @override
    def make_from_blueprint(
        cls,
        domain: str,
        pipe_code: str,
        blueprint: PipeParallelBlueprint,
        concept_codes_from_the_same_domain: list[str] | None = None,
    ) -> PipeParallel:
        parallel_sub_pipes: list[SubPipe] = []
        for sub_pipe_blueprint in blueprint.parallels:
            if not sub_pipe_blueprint.result:
                msg = f"Unexpected error in pipe '{pipe_code}': PipeParallel requires a result specified for each parallel sub pipe"
                raise PipeDefinitionError(
                    message=msg, domain_code=domain, pipe_code=pipe_code, description=blueprint.description, source=blueprint.source
                )
            sub_pipe = SubPipeFactory.make_from_blueprint(sub_pipe_blueprint, concept_codes_from_the_same_domain=concept_codes_from_the_same_domain)
            parallel_sub_pipes.append(sub_pipe)
        if not blueprint.add_each_output and not blueprint.combined_output:
            msg = (
                f"Unexpected error in pipe '{pipe_code}': PipeParallel requires either add_each_output to be True or combined_output to be set, "
                "or both, otherwise the pipe won't output anything"
            )
            raise PipeDefinitionError(
                message=msg, domain_code=domain, pipe_code=pipe_code, description=blueprint.description, source=blueprint.source
            )

        if blueprint.combined_output:
            combined_output_domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_code(
                domain=domain,
                concept_string_or_code=blueprint.output,
                concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
            )
            combined_output = get_required_concept(
                concept_string=ConceptFactory.make_concept_string_with_domain(
                    domain=combined_output_domain_and_code.domain,
                    concept_code=combined_output_domain_and_code.concept_code,
                ),
            )
        else:
            combined_output = None

        output_domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_code(
            domain=domain,
            concept_string_or_code=blueprint.output,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
        return PipeParallel(
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
            parallel_sub_pipes=parallel_sub_pipes,
            add_each_output=blueprint.add_each_output or False,
            combined_output=combined_output,
        )
