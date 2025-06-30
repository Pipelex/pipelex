from typing import Any, Dict, List, Optional

from typing_extensions import override

from pipelex.core.concept import Concept
from pipelex.core.pipe_blueprint import PipeBlueprint, PipeSpecificFactoryProtocol
from pipelex.core.pipe_input_spec import PipeInputSpec
from pipelex.exceptions import PipeDefinitionError
from pipelex.hub import get_concept_provider
from pipelex.pipe_controllers.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeBlueprint


class PipeParallelBlueprint(PipeBlueprint):
    parallels: List[SubPipeBlueprint]
    add_each_output: bool = True
    combined_output: Optional[str] = None


class PipeParallelFactory(PipeSpecificFactoryProtocol[PipeParallelBlueprint, PipeParallel]):
    @classmethod
    @override
    def make_pipe_from_blueprint(
        cls,
        domain_code: str,
        pipe_code: str,
        pipe_blueprint: PipeParallelBlueprint,
    ) -> PipeParallel:
        parallel_sub_pipes: List[SubPipe] = []
        for sub_pipe_blueprint in pipe_blueprint.parallels:
            if not sub_pipe_blueprint.result:
                raise PipeDefinitionError("PipeParallel requires a result specified for each parallel sub pipe")
            sub_pipe = sub_pipe_blueprint.make_sub_pipe()
            parallel_sub_pipes.append(sub_pipe)
        if not pipe_blueprint.add_each_output and not pipe_blueprint.combined_output:
            raise PipeDefinitionError("PipeParallel requires either add_each_output or combined_output to be set")
        if pipe_blueprint.combined_output and not Concept.concept_str_contains_domain(concept_str=pipe_blueprint.combined_output):
            pipe_blueprint.combined_output = domain_code + "." + pipe_blueprint.combined_output
            get_concept_provider().is_concept_code_legal(concept_code=pipe_blueprint.combined_output)

        return PipeParallel(
            domain=domain_code,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            inputs=PipeInputSpec(root=pipe_blueprint.inputs or {}),
            output_concept_code=pipe_blueprint.output,
            parallel_sub_pipes=parallel_sub_pipes,
            add_each_output=pipe_blueprint.add_each_output,
            combined_output=pipe_blueprint.combined_output,
        )

    @classmethod
    @override
    def make_pipe_from_details_dict(
        cls,
        domain_code: str,
        pipe_code: str,
        details_dict: Dict[str, Any],
    ) -> PipeParallel:
        pipe_blueprint = PipeParallelBlueprint.model_validate(details_dict)
        return cls.make_pipe_from_blueprint(
            domain_code=domain_code,
            pipe_code=pipe_code,
            pipe_blueprint=pipe_blueprint,
        )
