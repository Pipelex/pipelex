import pytest
from pydantic import ValidationError

from pipelex.core.pipes.pipe_blueprint import PipeType
from pipelex.pipe_signature.pipe_signature_blueprint import PipeSignatureBlueprint


class TestPipeSignatureBlueprintValidator:
    def test_blueprint_rejects_signature_for_pipe_signature(self) -> None:
        # `PipeSignature` is no longer a `PipeType` member, so Pydantic cannot coerce the string into
        # `signature_for` — the rejection is now structural, not a custom validator.
        with pytest.raises(ValidationError):
            PipeSignatureBlueprint(
                description="A signature cannot stand in for itself.",
                inputs={"doc": "Text"},
                output="Text",
                signature_for="PipeSignature",  # type: ignore[arg-type]
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

    def test_blueprint_is_signature_true(self) -> None:
        # Closes the base-False / subclass-True pair at the blueprint layer (otherwise only
        # exercised indirectly through the factory's `blueprint.is_signature` branch).
        blueprint = PipeSignatureBlueprint(
            description="A signature reports is_signature directly.",
            inputs={"doc": "Text"},
            output="Text",
        )
        assert blueprint.is_signature is True

    def test_blueprint_excludes_pipe_category_from_model_dump(self) -> None:
        # `pipe_category` is None and `Field(exclude=True)`, so it must never serialize into emitted
        # .mthds. This guards the `exclude=True` override independently of the JSON-schema exclusion
        # test (a separate Pydantic mechanism): dropping `exclude=True` would leak it here while the
        # schema test stayed green.
        blueprint = PipeSignatureBlueprint(
            description="A signature does not serialize a pipe_category.",
            inputs={"doc": "Text"},
            output="Text",
        )
        assert blueprint.pipe_category is None
        assert "pipe_category" not in blueprint.model_dump()
