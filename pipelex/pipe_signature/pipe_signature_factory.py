from typing import Any

from typing_extensions import override

from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.pipe_signature.pipe_signature_blueprint import PipeSignatureBlueprint
from pipelex.pipe_signature.pipe_signature_runtime import PipeSignatureRuntime


class PipeSignatureFactory(PipeFactoryProtocol[PipeSignatureBlueprint, PipeSignatureRuntime]):
    @classmethod
    @override
    def make(
        cls,
        pipe_category: Any,
        pipe_type: str,
        pipe_code: str,
        domain_code: str,
        description: str,
        inputs: InputStuffSpecs,
        output: StuffSpec,
        blueprint: PipeSignatureBlueprint,
    ) -> PipeSignatureRuntime:
        return PipeSignatureRuntime(
            domain_code=domain_code,
            code=pipe_code,
            description=description,
            inputs=inputs,
            output=output,
            signature_for=blueprint.signature_for,
        )
