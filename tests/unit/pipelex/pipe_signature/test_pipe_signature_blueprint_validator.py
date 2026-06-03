import pytest
from pydantic import ValidationError

from pipelex.core.pipes.pipe_blueprint import PipeType
from pipelex.pipe_signature.pipe_signature_blueprint import PipeSignatureBlueprint


class TestPipeSignatureBlueprintValidator:
    def test_blueprint_rejects_signature_for_pipe_signature(self) -> None:
        with pytest.raises(ValidationError):
            PipeSignatureBlueprint(
                description="A signature cannot stand in for itself.",
                inputs={"doc": "Text"},
                output="Text",
                signature_for=PipeType.PIPE_SIGNATURE,
            )

    def test_blueprint_accepts_signature_for_pipe_llm(self) -> None:
        blueprint = PipeSignatureBlueprint(
            description="A signature standing in for a PipeLLM.",
            inputs={"doc": "Text"},
            output="Text",
            signature_for=PipeType.PIPE_LLM,
        )
        assert blueprint.signature_for is PipeType.PIPE_LLM

    def test_blueprint_accepts_signature_for_none(self) -> None:
        blueprint = PipeSignatureBlueprint(
            description="A signature with no downstream hint.",
            inputs={"doc": "Text"},
            output="Text",
        )
        assert blueprint.signature_for is None
