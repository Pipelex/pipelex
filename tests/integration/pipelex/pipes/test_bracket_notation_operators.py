"""Integration tests for bracket notation in operator pipe factories."""

from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.pipe_operators.compose.pipe_compose_factory import PipeComposeFactory
from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint
from pipelex.pipe_operators.extract.pipe_extract_factory import PipeExtractFactory
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_operators.func.pipe_func_factory import PipeFuncFactory
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.pipe_operators.img_gen.pipe_img_gen_factory import PipeImgGenFactory
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_operators.llm.pipe_llm_factory import PipeLLMFactory


class TestBracketNotationInOperators:
    """Test that operator factories correctly handle bracket notation in inputs and outputs."""

    def test_pipe_llm_with_bracket_output_variable_list(self):
        """Test PipeLLM factory with variable list output (Text[])."""
        blueprint = PipeLLMBlueprint(
            description="Generate multiple items",
            inputs={"topic": NativeConceptCode.TEXT},
            output=f"{NativeConceptCode.TEXT}[]",
            prompt="Generate items about $topic",
        )

        pipe = PipeLLMFactory.make_from_blueprint(
            domain="test",
            pipe_code="test_llm",
            blueprint=blueprint,
        )

        assert pipe.output.code == "Text"
        assert pipe.output_multiplicity is True

    def test_pipe_llm_with_bracket_output_fixed_count(self):
        """Test PipeLLM factory with fixed count output (Text[5])."""
        blueprint = PipeLLMBlueprint(
            description="Generate exactly 5 items",
            inputs={},
            output=f"{NativeConceptCode.TEXT}[5]",
            prompt="Generate 5 items",
        )

        pipe = PipeLLMFactory.make_from_blueprint(
            domain="test",
            pipe_code="test_llm",
            blueprint=blueprint,
        )

        assert pipe.output.code == "Text"
        assert pipe.output_multiplicity == 5

    def test_pipe_llm_with_bracket_inputs(self):
        """Test PipeLLM factory with bracket notation in inputs."""
        blueprint = PipeLLMBlueprint(
            description="Process multiple documents",
            inputs={"documents": f"{NativeConceptCode.TEXT}[]", "query": NativeConceptCode.TEXT},
            output=NativeConceptCode.TEXT,
            prompt="Summarize @documents based on $query",
        )

        pipe = PipeLLMFactory.make_from_blueprint(
            domain="test",
            pipe_code="test_llm",
            blueprint=blueprint,
        )

        assert "documents" in pipe.inputs.root
        assert "query" in pipe.inputs.root
        assert pipe.inputs.root["documents"].multiplicity is True
        assert pipe.inputs.root["query"].multiplicity is None

    def test_pipe_img_gen_with_bracket_output(self):
        """Test PipeImgGen factory with fixed count output (Image[3])."""
        blueprint = PipeImgGenBlueprint(
            description="Generate 3 images",
            inputs={"prompt": NativeConceptCode.TEXT},
            output=f"{NativeConceptCode.IMAGE}[3]",
        )

        pipe = PipeImgGenFactory.make_from_blueprint(
            domain="test",
            pipe_code="test_img_gen",
            blueprint=blueprint,
        )

        assert pipe.output.code == "Image"
        assert pipe.output_multiplicity == 3

    def test_pipe_func_with_bracket_input_and_output(self):
        """Test PipeFunc factory with bracket notation."""
        blueprint = PipeFuncBlueprint(
            description="Process items",
            inputs={"items": f"{NativeConceptCode.TEXT}[2]"},
            output=f"{NativeConceptCode.TEXT}[]",
            function_name="process_function",
        )

        pipe = PipeFuncFactory.make_from_blueprint(
            domain="test",
            pipe_code="test_func",
            blueprint=blueprint,
        )

        assert pipe.inputs.root["items"].multiplicity == 2
        assert pipe.output.code == "Text"

    def test_pipe_compose_with_bracket_notation(self):
        """Test PipeCompose factory with bracket notation."""
        blueprint = PipeComposeBlueprint(
            description="Compose multiple items",
            inputs={"items": f"{NativeConceptCode.TEXT}[]"},
            output=NativeConceptCode.TEXT,
            template="<ul>{% for item in items %}<li>{{ item }}</li>{% endfor %}</ul>",
        )

        pipe = PipeComposeFactory.make_from_blueprint(
            domain="test",
            pipe_code="test_compose",
            blueprint=blueprint,
        )

        assert pipe.inputs.root["items"].multiplicity is True
        assert pipe.output.code == "Text"

    def test_pipe_extract_with_bracket_output(self):
        """Test PipeExtract factory with bracket notation in output."""
        blueprint = PipeExtractBlueprint(
            description="Extract pages",
            inputs={"document": NativeConceptCode.PDF},
            output=f"{NativeConceptCode.PAGE}[]",  # Extract returns list of pages
        )

        pipe = PipeExtractFactory.make_from_blueprint(
            domain="test",
            pipe_code="test_extract",
            blueprint=blueprint,
        )

        assert pipe.output.code == "Page"
