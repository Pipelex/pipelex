import json

from kajson import kajson

from pipelex.pipe_controllers.binding.binding_step_blueprint import BINDING_FROM_KEY, BindingStepBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class TestBindingStepKajsonRoundtrip:
    """A binding step crosses a process boundary inside the library crate a run carries, which kajson encodes.

    kajson encodes a model through its ``__dict__``, under its field names, so the path would travel as
    ``from_path``, which the blueprint refuses on the way back in. These tests pin the encoding to ``from``.
    """

    def test_binding_step_blueprint_roundtrips(self) -> None:
        original = BindingStepBlueprint.model_validate({BINDING_FROM_KEY: "invoice.total", "result": "total_amount"})

        serialized = kajson.dumps(original)  # pyright: ignore[reportUnknownMemberType]
        deserialized = kajson.loads(serialized)  # pyright: ignore[reportUnknownMemberType]

        assert isinstance(deserialized, BindingStepBlueprint)
        assert deserialized == original

    def test_binding_step_blueprint_is_encoded_under_from(self) -> None:
        original = BindingStepBlueprint.model_validate({BINDING_FROM_KEY: "invoice.total", "result": "total_amount"})

        encoded = json.loads(kajson.dumps(original))  # pyright: ignore[reportUnknownMemberType]

        assert encoded[BINDING_FROM_KEY] == "invoice.total"
        assert "from_path" not in encoded

    def test_sequence_blueprint_with_a_binding_step_roundtrips(self) -> None:
        original = PipeSequenceBlueprint(
            description="Acknowledges an invoice by its total",
            inputs={"invoice": "Invoice"},
            output="Text",
            steps=[
                BindingStepBlueprint.model_validate({BINDING_FROM_KEY: "invoice.total", "result": "total_amount"}),
                SubPipeBlueprint(pipe="write_receipt", result="receipt"),
            ],
        )

        serialized = kajson.dumps(original)  # pyright: ignore[reportUnknownMemberType]
        deserialized = kajson.loads(serialized)  # pyright: ignore[reportUnknownMemberType]

        assert isinstance(deserialized, PipeSequenceBlueprint)
        assert deserialized == original
        assert isinstance(deserialized.steps[0], BindingStepBlueprint)
        assert deserialized.steps[0].from_path == "invoice.total"
