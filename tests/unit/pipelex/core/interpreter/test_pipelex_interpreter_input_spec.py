from typing import Any

import pytest

from pipelex.core.interpreter import PipelexInterpreter
from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint


class TestPipelexInterpreterInputSpec:
    def test_inputs_to_plx_string_simple_strings(self):
        # Simple string inputs (like "Text")
        simple_inputs = {"text": "Text", "topic": "Text"}

        result = PipelexInterpreter.inputs_to_plx_string(simple_inputs)

        expected = '{ text = "Text", topic = "Text" }'
        assert result == expected

    def test_inputs_to_plx_string_input_requirement_blueprints(self):
        # InputRequirementBlueprint inputs
        complex_inputs = {
            "text": InputRequirementBlueprint(concept="Text", multiplicity=1),
            "problem": InputRequirementBlueprint(concept="Text"),  # multiplicity=None
            "documents": InputRequirementBlueprint(concept="Text", multiplicity=True),
            "query": InputRequirementBlueprint(concept="Text", multiplicity=False),
        }

        result = PipelexInterpreter.inputs_to_plx_string(complex_inputs)

        expected = (
            '{ text = { concept = "Text", multiplicity = 1 }, problem = { concept = "Text" }, '
            'documents = { concept = "Text", multiplicity = true }, query = { concept = "Text", multiplicity = false } }'
        )
        assert result == expected

    @pytest.mark.parametrize(
        "input_req,expected",
        [
            # Test with just concept (multiplicity=None should not be included)
            (InputRequirementBlueprint(concept="Text"), {"concept": "Text"}),
            # Test with concept and multiplicity=1
            (InputRequirementBlueprint(concept="Text", multiplicity=1), {"concept": "Text", "multiplicity": 1}),
            # Test with concept and multiplicity=True
            (InputRequirementBlueprint(concept="Text", multiplicity=True), {"concept": "Text", "multiplicity": True}),
            # Test with concept and multiplicity=False
            (InputRequirementBlueprint(concept="Text", multiplicity=False), {"concept": "Text", "multiplicity": False}),
            # Test with different concept
            (InputRequirementBlueprint(concept="Image", multiplicity=5), {"concept": "Image", "multiplicity": 5}),
        ],
    )
    def test_serialize_input_requirement(self, input_req: InputRequirementBlueprint, expected: dict[str, Any]):
        result = PipelexInterpreter.serialize_input_requirement(input_req)
        assert result == expected
