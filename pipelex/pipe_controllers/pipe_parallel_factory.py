from typing import List, Literal, Optional

from typing_extensions import override

from pipelex.core.concepts.concept import Concept, NativeConceptEnum
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


class PipeParallelFactory(PipeFactoryProtocol[PipeParallelBlueprint, PipeParallel]):
    @classmethod
    @override
    def make_from_blueprint(
        cls,
        domain: str,
        pipe_code: str,
        pipe_blueprint: PipeParallelBlueprint,
    ) -> PipeParallel:
        parallel_sub_pipes: List[SubPipe] = []
        for sub_pipe_blueprint in pipe_blueprint.parallels:
            if not sub_pipe_blueprint.result:
                raise PipeDefinitionError("PipeParallel requires a result specified for each parallel sub pipe")
            sub_pipe = SubPipeFactory.make_from_blueprint(sub_pipe_blueprint)
            parallel_sub_pipes.append(sub_pipe)
        if not pipe_blueprint.add_each_output and not pipe_blueprint.combined_output:
            raise PipeDefinitionError("PipeParallel requires either add_each_output or combined_output to be set")

        output_concept_code = pipe_blueprint.output
        if "." not in output_concept_code:
            if Concept.is_native_concept_code(concept_code=output_concept_code):
                output = get_concept_provider().get_native_concept(native_concept=NativeConceptEnum(output_concept_code))
            else:
                output = get_concept_provider().get_required_concept(
                    concept_string=Concept.construct_concept_string_with_domain(domain=domain, concept_code=output_concept_code)
                )
        else:
            output = get_concept_provider().get_required_concept(concept_string=output_concept_code)

        if pipe_blueprint.combined_output:
            if pipe_blueprint.combined_output and "." not in pipe_blueprint.combined_output:
                if Concept.is_native_concept_code(concept_code=pipe_blueprint.combined_output):
                    combined_output = get_concept_provider().get_native_concept(native_concept=NativeConceptEnum(pipe_blueprint.combined_output))
                else:
                    combined_output = get_concept_provider().get_required_concept(
                        concept_string=Concept.construct_concept_string_with_domain(domain=domain, concept_code=output_concept_code)
                    )
            else:
                combined_output = get_concept_provider().get_required_concept(concept_string=output_concept_code)
        else:
            combined_output = None

        return PipeParallel(
            domain=domain,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            inputs=PipeInputSpecFactory.make_from_blueprint(domain=domain, blueprint=pipe_blueprint.inputs or {}),
            output=output,
            parallel_sub_pipes=parallel_sub_pipes,
            add_each_output=pipe_blueprint.add_each_output,
            combined_output=combined_output,
        )
