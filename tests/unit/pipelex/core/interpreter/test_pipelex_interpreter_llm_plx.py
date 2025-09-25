import pytest

from pipelex.core.interpreter import PipelexInterpreter
from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


class TestPipelexInterpreterLLMPLX:
    @pytest.mark.parametrize(
        "pipe_name,blueprint,expected_plx",
        [
            # Simple LLM pipe with string inputs
            (
                "simple_llm",
                PipeLLMBlueprint(
                    type="PipeLLM",
                    definition="Simple text generation",
                    inputs={"text": "Text", "topic": "Text"},
                    output="Text",
                    prompt_template="Generate text about $topic based on: @text",
                ),
                """[pipe.simple_llm]
type = "PipeLLM"
definition = "Simple text generation"
inputs = { text = "Text", topic = "Text" }
output = "Text"
prompt_template = "Generate text about $topic based on: @text\"""",
            ),
            # LLM pipe with complex inputs (InputRequirementBlueprint)
            (
                "complex_llm",
                PipeLLMBlueprint(
                    type="PipeLLM",
                    definition="Extract structured information",
                    inputs={
                        "documents": InputRequirementBlueprint(concept="Text", multiplicity=True),
                        "query": InputRequirementBlueprint(concept="Text", multiplicity=False),
                    },
                    output="DocumentSummary",
                    prompt_template="Extract information from documents: @documents based on query: $query",
                ),
                """[pipe.complex_llm]
type = "PipeLLM"
definition = "Extract structured information"
inputs = { documents = { concept = "Text", multiplicity = true }, query = { concept = "Text", multiplicity = false } }
output = "DocumentSummary"
prompt_template = "Extract information from documents: @documents based on query: $query\"""",
            ),
            # LLM pipe with system prompt
            (
                "system_prompt_llm",
                PipeLLMBlueprint(
                    type="PipeLLM",
                    definition="Analysis with system prompt",
                    inputs={"content": "Text"},
                    output="Text",
                    system_prompt_template="You are an expert analyst with $expertise_level knowledge",
                    prompt_template="Analyze this content: @content",
                ),
                """[pipe.system_prompt_llm]
type = "PipeLLM"
definition = "Analysis with system prompt"
inputs = { content = "Text" }
output = "Text"
system_prompt_template = "You are an expert analyst with $expertise_level knowledge"
prompt_template = "Analyze this content: @content\"""",
            ),
            # LLM pipe with nb_output
            (
                "multiple_output_llm",
                PipeLLMBlueprint(
                    type="PipeLLM",
                    definition="Generate multiple outputs",
                    inputs={"topic": "Text"},
                    output="Text",
                    nb_output=3,
                    prompt_template="Generate ideas about: $topic",
                ),
                """[pipe.multiple_output_llm]
type = "PipeLLM"
definition = "Generate multiple outputs"
inputs = { topic = "Text" }
output = "Text"
nb_output = 3
prompt_template = "Generate ideas about: $topic\"""",
            ),
        ],
    )
    def test_llm_pipe_to_plx_string(self, pipe_name: str, blueprint: PipeLLMBlueprint, expected_plx: str):
        result = PipelexInterpreter.llm_pipe_to_plx_string(pipe_name, blueprint)
        assert result == expected_plx
