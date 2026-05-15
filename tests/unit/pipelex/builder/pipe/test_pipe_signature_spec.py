import pytest
from pydantic import ValidationError

from pipelex.builder.pipe.pipe_signature_spec import PipeSignatureSpec
from pipelex.core.pipes.pipe_blueprint import PipeType
from pipelex.pipe_signature.pipe_signature_blueprint import PipeSignatureBlueprint


def _make_minimal_signature(**overrides: object) -> PipeSignatureSpec:
    kwargs: dict[str, object] = {
        "pipe_code": "sig_pipe",
        "description": "A signature.",
        "inputs": {"doc": "Document"},
        "output": "Summary",
    }
    kwargs.update(overrides)
    return PipeSignatureSpec(**kwargs)  # type: ignore[arg-type]


class TestPipeSignatureSpec:
    def test_type_literal_is_pipe_signature(self) -> None:
        sig = _make_minimal_signature()
        assert sig.type == "PipeSignature"

    def test_signature_for_optional(self) -> None:
        no_hint = _make_minimal_signature()
        assert no_hint.signature_for is None
        with_hint = _make_minimal_signature(signature_for=PipeType.PIPE_LLM)
        assert with_hint.signature_for is PipeType.PIPE_LLM

    def test_signature_for_rejects_pipe_signature(self) -> None:
        with pytest.raises(ValidationError):
            _make_minimal_signature(signature_for=PipeType.PIPE_SIGNATURE)

    def test_inputs_accept_multiplicity(self) -> None:
        var_list = _make_minimal_signature(inputs={"docs": "Document[]"})
        assert var_list.inputs == {"docs": "Document[]"}
        fixed_list = _make_minimal_signature(inputs={"images": "Image[3]"})
        assert fixed_list.inputs == {"images": "Image[3]"}

    def test_inputs_reject_invalid_concept_syntax(self) -> None:
        with pytest.raises(ValidationError):
            _make_minimal_signature(inputs={"bad": "lowercase"})

    def test_no_result_field(self) -> None:
        assert "result" not in PipeSignatureSpec.model_fields

    def test_to_blueprint_returns_signature_blueprint(self) -> None:
        sig = _make_minimal_signature(signature_for=PipeType.PIPE_LLM)
        blueprint = sig.to_blueprint()
        assert isinstance(blueprint, PipeSignatureBlueprint)
        assert blueprint.description == sig.description
        assert blueprint.inputs == sig.inputs
        assert blueprint.output == sig.output
        assert blueprint.signature_for is PipeType.PIPE_LLM

    def test_to_blueprint_preserves_input_multiplicity(self) -> None:
        sig = _make_minimal_signature(inputs={"docs": "Document[]"})
        blueprint = sig.to_blueprint()
        assert blueprint.inputs == {"docs": "Document[]"}
