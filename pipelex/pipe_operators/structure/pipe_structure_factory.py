from typing import Any

from typing_extensions import override

from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.variable_multiplicity import make_variable_multiplicity, parse_concept_with_multiplicity
from pipelex.pipe_machinery.pipe_factory import PipeFactoryProtocol
from pipelex.pipe_operators.structure.pipe_structure import PipeStructure
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint


class PipeStructureFactory(PipeFactoryProtocol[PipeStructureBlueprint, PipeStructure]):
    @classmethod
    @override
    def make(
        cls,
        *,
        pipe_category: Any,
        pipe_type: str,
        pipe_code: str,
        domain_code: str,
        description: str,
        inputs: InputStuffSpecs,
        output: StuffSpec,
        blueprint: PipeStructureBlueprint,
    ) -> PipeStructure:
        # `PipeStructureBlueprint.validate_inputs` already enforces exactly one input.
        text_input_name = blueprint.input_names[0]

        output_parse_result = parse_concept_with_multiplicity(blueprint.output)
        output_multiplicity = make_variable_multiplicity(
            nb_items=output_parse_result.multiplicity if isinstance(output_parse_result.multiplicity, int) else None,
            multiple_items=output_parse_result.multiplicity if isinstance(output_parse_result.multiplicity, bool) else None,
        )

        return PipeStructure(
            domain_code=domain_code,
            code=pipe_code,
            description=description,
            inputs=inputs,
            output=output,
            llm_choice=blueprint.model,
            text_input_name=text_input_name,
            output_multiplicity=output_multiplicity,
        )
