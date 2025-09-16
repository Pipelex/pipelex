"""Unit tests for PipelexInterpreter serialize functions."""

from typing import Any, Dict

from pipelex.cogt.ocr.ocr_handle import OcrHandle
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint, ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.core.pipes.pipe_input_spec_blueprint import InputRequirementBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_operators.ocr.pipe_ocr_blueprint import PipeOcrBlueprint


class TestSerializeInputRequirement:
    """Test _serialize_input_requirement function."""

    def test_serialize_input_requirement_basic(self):
        """Test serializing basic InputRequirementBlueprint."""
        input_req = InputRequirementBlueprint(concept="Text")
        result = PipelexInterpreter.serialize_input_requirement(input_req)

        expected = {"concept": "Text"}
        assert result == expected

    def test_serialize_input_requirement_with_multiplicity_int(self):
        """Test serializing InputRequirementBlueprint with integer multiplicity."""
        input_req = InputRequirementBlueprint(concept="Text", multiplicity=3)
        result = PipelexInterpreter.serialize_input_requirement(input_req)

        expected = {"concept": "Text", "multiplicity": 3}
        assert result == expected

    def test_serialize_input_requirement_with_multiplicity_bool(self):
        """Test serializing InputRequirementBlueprint with boolean multiplicity."""
        input_req = InputRequirementBlueprint(concept="Text", multiplicity=True)
        result = PipelexInterpreter.serialize_input_requirement(input_req)

        expected = {"concept": "Text", "multiplicity": True}
        assert result == expected


class TestSerializeInputs:
    """Test _serialize_inputs function."""

    def test_serialize_inputs_mixed_types(self):
        """Test serializing mixed input types."""
        inputs: Dict[str, str | InputRequirementBlueprint] = {
            "text": "Text",
            "data": InputRequirementBlueprint(concept="Data", multiplicity=2),
            "query": InputRequirementBlueprint(concept="Text"),
        }
        result = PipelexInterpreter.serialize_inputs(inputs)

        expected = {"text": "Text", "data": {"concept": "Data", "multiplicity": 2}, "query": {"concept": "Text"}}
        assert result == expected

    def test_serialize_inputs_empty(self):
        """Test serializing empty inputs."""
        inputs: Dict[str, Any] = {}
        result = PipelexInterpreter.serialize_inputs(inputs)

        assert result == {}


class TestSerializeConceptStructure:
    """Test concept structure serialization functions."""

    def test_serialize_concept_structure_field_string(self):
        """Test serializing string concept structure field."""
        field_value = "Simple description"
        result = PipelexInterpreter.serialize_concept_structure_field(field_value)

        assert result == "Simple description"

    def test_serialize_concept_structure_field_blueprint(self):
        """Test serializing ConceptStructureBlueprint field."""
        field_value = ConceptStructureBlueprint(definition="A text field", type=ConceptStructureBlueprintFieldType.TEXT, required=True)
        result = PipelexInterpreter.serialize_concept_structure_field(field_value)

        expected = {"definition": "A text field", "required": True, "type": "text"}
        assert result == expected

    def test_serialize_concept_structure_field_blueprint_with_all_fields(self):
        """Test serializing ConceptStructureBlueprint with all optional fields."""
        field_value = ConceptStructureBlueprint(
            definition="A complex field",
            type=ConceptStructureBlueprintFieldType.DICT,
            key_type="string",
            value_type="integer",
            choices=["option1", "option2"],
            required=False,
            default_value={"default": 42},
        )
        result = PipelexInterpreter.serialize_concept_structure_field(field_value)

        expected = {
            "definition": "A complex field",
            "required": False,
            "type": "dict",
            "key_type": "string",
            "value_type": "integer",
            "choices": ["option1", "option2"],
            "default_value": {"default": 42},
        }
        assert result == expected

    def test_serialize_concept_structure_string(self):
        """Test serializing string concept structure."""
        structure = "Simple structure"
        result = PipelexInterpreter.serialize_concept_structure(structure)

        assert result == "Simple structure"

    def test_serialize_concept_structure_dict(self):
        """Test serializing dict concept structure."""
        structure = {
            "name": "Person's name",
            "age": ConceptStructureBlueprint(definition="Person's age", type=ConceptStructureBlueprintFieldType.INTEGER, required=True),
        }
        result = PipelexInterpreter.serialize_concept_structure(structure)

        expected = {
            "name": "Person's name",
            "age": {"definition": "Person's age", "required": True, "type": "integer"},
        }
        assert result == expected


class TestSerializeSingleConcept:
    """Test _serialize_single_concept function."""

    def test_serialize_single_concept_string(self):
        """Test serializing string concept."""
        concept = "Simple concept definition"
        result = PipelexInterpreter.serialize_single_concept(concept)

        assert result == "Simple concept definition"

    def test_serialize_single_concept_simple_definition(self):
        """Test serializing ConceptBlueprint with just definition."""
        concept = ConceptBlueprint(definition="A simple concept")
        result = PipelexInterpreter.serialize_single_concept(concept)

        assert result == "A simple concept"

    def test_serialize_single_concept_with_refines(self):
        """Test serializing ConceptBlueprint with refines."""
        concept = ConceptBlueprint(definition="A specialized text", refines="Text")
        result = PipelexInterpreter.serialize_single_concept(concept)

        expected = {"definition": "A specialized text", "refines": "Text"}
        assert result == expected

    def test_serialize_single_concept_with_structure(self):
        """Test serializing ConceptBlueprint with structure."""
        concept = ConceptBlueprint(
            definition="A person",
            structure={
                "name": "Person's name",
                "age": ConceptStructureBlueprint(definition="Person's age", type=ConceptStructureBlueprintFieldType.INTEGER, required=True),
            },
        )
        result = PipelexInterpreter.serialize_single_concept(concept)

        expected = {
            "definition": "A person",
            "structure": {
                "name": "Person's name",
                "age": {"definition": "Person's age", "required": True, "type": "integer"},
            },
        }
        assert result == expected


class TestSerializeConcepts:
    """Test _serialize_concepts function."""

    def test_serialize_concepts_empty(self):
        """Test serializing empty concepts."""
        result = PipelexInterpreter.serialize_concepts(None, "test_domain")
        assert result == {}

    def test_serialize_concepts_mixed(self):
        """Test serializing mixed concept types."""
        concepts: Dict[str, ConceptBlueprint | str] = {
            "SimpleText": "A simple text concept",
            "PersonInfo": ConceptBlueprint(definition="Information about a person", refines="Text"),
            "StructuredData": ConceptBlueprint(
                definition="Structured data",
                structure={
                    "title": "Data title",
                    "value": ConceptStructureBlueprint(definition="Data value", type=ConceptStructureBlueprintFieldType.NUMBER, required=True),
                },
            ),
        }
        result = PipelexInterpreter.serialize_concepts(concepts, "test_domain")

        expected = {
            "SimpleText": "A simple text concept",
            "PersonInfo": {"definition": "Information about a person", "refines": "Text"},
            "StructuredData": {
                "definition": "Structured data",
                "structure": {
                    "title": "Data title",
                    "value": {"definition": "Data value", "required": True, "type": "number"},
                },
            },
        }
        assert result == expected


class TestSerializeSubPipe:
    """Test _serialize_sub_pipe function."""

    def test_serialize_sub_pipe_basic(self):
        """Test serializing basic sub pipe."""
        sub_pipe = SubPipeBlueprint(pipe="test_pipe", result="test_result")
        result = PipelexInterpreter.serialize_sub_pipe(sub_pipe)

        expected = {"pipe": "test_pipe", "result": "test_result"}
        assert result == expected

    def test_serialize_sub_pipe_with_nb_output_and_batch(self):
        """Test serializing sub pipe with nb_output and batch fields."""
        sub_pipe = SubPipeBlueprint(pipe="test_pipe", result="test_result", nb_output=3, batch_over="input_list", batch_as="current_item")
        result = PipelexInterpreter.serialize_sub_pipe(sub_pipe)

        expected = {"pipe": "test_pipe", "result": "test_result", "nb_output": 3, "batch_over": "input_list", "batch_as": "current_item"}
        assert result == expected

    def test_serialize_sub_pipe_with_multiple_output_and_batch(self):
        """Test serializing sub pipe with multiple_output and batch fields."""
        sub_pipe = SubPipeBlueprint(pipe="test_pipe", result="test_result", multiple_output=True, batch_over="input_list", batch_as="current_item")
        result = PipelexInterpreter.serialize_sub_pipe(sub_pipe)

        expected = {"pipe": "test_pipe", "result": "test_result", "multiple_output": True, "batch_over": "input_list", "batch_as": "current_item"}
        assert result == expected

    def test_serialize_sub_pipe_skip_defaults(self):
        """Test that default values are not included in serialization."""
        sub_pipe = SubPipeBlueprint(
            pipe="test_pipe",
            result="test_result",
            batch_over=False,  # Default value
            batch_as=None,  # Default value
        )
        result = PipelexInterpreter.serialize_sub_pipe(sub_pipe)

        expected = {"pipe": "test_pipe", "result": "test_result"}
        assert result == expected


class TestSerializePipeBlueprints:
    """Test individual pipe blueprint serialization functions."""

    def test_serialize_llm_pipe_basic(self):
        """Test serializing basic PipeLLM blueprint."""
        pipe = PipeLLMBlueprint(type="PipeLLM", definition="Generate text using LLM", output="Text", prompt_template="Generate a story")
        result = PipelexInterpreter.serialize_llm_pipe(pipe, "test_domain")

        expected = {"type": "PipeLLM", "definition": "Generate text using LLM", "output": "Text", "prompt_template": "Generate a story"}
        assert result == expected

    def test_serialize_llm_pipe_with_inputs_and_options(self):
        """Test serializing PipeLLM blueprint with inputs and optional fields."""
        pipe = PipeLLMBlueprint(
            type="PipeLLM",
            definition="Extract information",
            inputs={"text": "Text", "topic": InputRequirementBlueprint(concept="Text", multiplicity=1)},
            output="ExtractedInfo",
            system_prompt="You are an expert extractor",
            prompt_template="Extract info about $topic from @text",
            nb_output=2,
        )
        result = PipelexInterpreter.serialize_llm_pipe(pipe, "test_domain")

        expected = {
            "type": "PipeLLM",
            "definition": "Extract information",
            "inputs": {"text": "Text", "topic": {"concept": "Text", "multiplicity": 1}},
            "output": "ExtractedInfo",
            "nb_output": 2,
            "system_prompt": "You are an expert extractor",
            "prompt_template": "Extract info about $topic from @text",
        }
        assert result == expected

    def test_serialize_ocr_pipe_basic(self):
        """Test serializing basic PipeOcr blueprint."""
        pipe = PipeOcrBlueprint(type="PipeOcr", definition="Extract text from PDF", output="Page", ocr_handle=OcrHandle.BASIC_OCR)
        result = PipelexInterpreter.serialize_ocr_pipe(pipe, "test_domain")

        expected = {"type": "PipeOcr", "definition": "Extract text from PDF", "output": "Page", "ocr_handle": "basic/pypdfium2"}
        assert result == expected

    def test_serialize_sequence_pipe_basic(self):
        """Test serializing basic PipeSequence blueprint."""
        pipe = PipeSequenceBlueprint(
            type="PipeSequence",
            definition="Process in sequence",
            output="Result",
            steps=[SubPipeBlueprint(pipe="step1", result="result1"), SubPipeBlueprint(pipe="step2", result="result2")],
        )
        result = PipelexInterpreter.serialize_sequence_pipe(pipe, "test_domain")

        expected = {
            "type": "PipeSequence",
            "definition": "Process in sequence",
            "output": "Result",
            "steps": [{"pipe": "step1", "result": "result1"}, {"pipe": "step2", "result": "result2"}],
        }
        assert result == expected


class TestAddCommonPipeFields:
    """Test _add_common_pipe_fields helper function."""

    def test_add_common_pipe_fields_with_inputs(self):
        """Test adding common pipe fields when inputs exist."""
        result: Dict[str, Any] = {"type": "TestPipe"}

        # Mock pipe with inputs
        class MockPipe:
            def __init__(self):
                self.inputs = {"text": "Text", "data": InputRequirementBlueprint(concept="Data")}

        pipe = MockPipe()
        PipelexInterpreter.add_common_pipe_fields(result, pipe)

        expected = {"type": "TestPipe", "inputs": {"text": "Text", "data": {"concept": "Data"}}}
        assert result == expected

    def test_add_common_pipe_fields_without_inputs(self):
        """Test adding common pipe fields when no inputs exist."""
        result: Dict[str, Any] = {"type": "TestPipe"}

        # Mock pipe without inputs
        class MockPipe:
            def __init__(self):
                self.inputs = None

        pipe = MockPipe()
        PipelexInterpreter.add_common_pipe_fields(result, pipe)

        expected = {"type": "TestPipe"}
        assert result == expected

    def test_add_common_pipe_fields_no_inputs_attribute(self):
        """Test adding common pipe fields when pipe has no inputs attribute."""
        result: Dict[str, Any] = {"type": "TestPipe"}

        # Mock pipe without inputs attribute
        class MockPipe:
            pass

        pipe = MockPipe()
        PipelexInterpreter.add_common_pipe_fields(result, pipe)

        expected = {"type": "TestPipe"}
        assert result == expected
