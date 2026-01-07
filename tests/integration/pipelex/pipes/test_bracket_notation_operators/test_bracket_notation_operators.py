from pathlib import Path
from typing import Callable

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.pipe_operators.extract.pipe_extract import PipeExtract
from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_operators.img_gen.pipe_img_gen import PipeImgGen
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.system.registries.func_registry import pipe_func


# Test function for PipeFunc bracket notation test
@pipe_func(name="process_function")
def process_function(working_memory: WorkingMemory) -> ListContent[TextContent]:
    """Test function that processes items and returns a list."""
    items = working_memory.get_stuff_as_list(name="two_texts", item_type=TextContent).items
    # Process items and return as list
    # result_items = [TextContent(text=f"processed: {item.text}") for item in items.content.items]
    processed_items = [TextContent(text=f"processed: {item.text}") for item in items]
    return ListContent(items=processed_items)


class TestBracketNotationInOperators:
    """Test that operator factories correctly handle bracket notation in inputs and outputs."""

    def test_pipe_llm_with_bracket_output_variable_list(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test PipeLLM factory with variable list output (Text[])."""
        blueprint = PipeLLMBlueprint(
            description="Generate multiple items",
            inputs={"topic": NativeConceptCode.TEXT},
            output=f"{NativeConceptCode.TEXT}[]",
            prompt="Generate items about $topic",
        )

        pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test",
            pipe_code="test_llm",
            blueprint=blueprint,
        )

        assert pipe.output.concept.code == "Text"
        assert pipe.output_multiplicity is True

    def test_pipe_llm_with_bracket_output_fixed_count(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test PipeLLM factory with fixed count output (Text[5])."""
        blueprint = PipeLLMBlueprint(
            description="Generate exactly 5 items",
            inputs={},
            output=f"{NativeConceptCode.TEXT}[5]",
            prompt="Generate 5 items",
        )

        pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test",
            pipe_code="test_llm",
            blueprint=blueprint,
        )

        assert pipe.output.concept.code == "Text"
        assert pipe.output_multiplicity == 5

    def test_pipe_llm_with_bracket_inputs(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test PipeLLM factory with bracket notation in inputs."""
        blueprint = PipeLLMBlueprint(
            description="Process multiple documents",
            inputs={"documents": f"{NativeConceptCode.TEXT}[]", "query": NativeConceptCode.TEXT},
            output=NativeConceptCode.TEXT,
            prompt="Summarize @documents based on $query",
        )

        pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test",
            pipe_code="test_llm",
            blueprint=blueprint,
        )

        assert "documents" in pipe.inputs.root
        assert "query" in pipe.inputs.root
        assert pipe.inputs.root["documents"].multiplicity is True
        assert pipe.inputs.root["query"].multiplicity is None

    def test_pipe_img_gen_with_bracket_output(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test PipeImgGen factory with fixed count output (Image[3])."""
        blueprint = PipeImgGenBlueprint(
            description="Generate 3 images",
            inputs={"prompt": NativeConceptCode.TEXT},
            output=f"{NativeConceptCode.IMAGE}[3]",
            prompt="@prompt",
        )

        pipe = PipeFactory[PipeImgGen].make_from_blueprint(
            domain_code="test",
            pipe_code="test_img_gen",
            blueprint=blueprint,
        )

        assert pipe.output.concept.code == "Image"
        assert pipe.output_multiplicity == 3

    def test_pipe_func_with_bracket_input_and_output(self, load_test_library: Callable[[list[Path]], None]):
        load_test_library([Path(Path(__file__).parent)])

        blueprint = PipeFuncBlueprint(
            description="Process items",
            inputs={"two_texts": f"{NativeConceptCode.TEXT}[2]"},
            output=f"{NativeConceptCode.TEXT}[]",
            function_name="process_function",
        )

        pipe = PipeFactory[PipeFunc].make_from_blueprint(
            domain_code="test",
            pipe_code="test_func",
            blueprint=blueprint,
        )

        assert pipe.inputs.root["two_texts"].multiplicity == 2
        assert pipe.output.concept.code == "Text"

    def test_pipe_compose_with_bracket_notation(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test PipeCompose factory with bracket notation."""
        blueprint = PipeComposeBlueprint(
            description="Compose multiple items",
            inputs={"items": f"{NativeConceptCode.TEXT}[]"},
            output=NativeConceptCode.TEXT,
            template="<ul>{% for item in items %}<li>{{ item }}</li>{% endfor %}</ul>",
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="test",
            pipe_code="test_compose",
            blueprint=blueprint,
        )

        assert pipe.inputs.root["items"].multiplicity is True
        assert pipe.output.concept.code == "Text"

    def test_pipe_extract_with_bracket_output(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test PipeExtract factory with bracket notation in output."""
        blueprint = PipeExtractBlueprint(
            description="Extract pages",
            inputs={"document": NativeConceptCode.DOCUMENT},
            output=f"{NativeConceptCode.PAGE}[]",  # Extract returns list of pages
        )

        pipe = PipeFactory[PipeExtract].make_from_blueprint(
            domain_code="test",
            pipe_code="test_extract",
            blueprint=blueprint,
        )

        assert pipe.output.concept.code == "Page"
