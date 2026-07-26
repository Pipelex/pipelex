from typing import TYPE_CHECKING, Any, Callable

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_concept_library, get_native_concept
from tests.cases.images import ImageTestCases

if TYPE_CHECKING:
    from mthds.protocol.pipeline_inputs import PipelineInputs


class TestWorkingMemoryFactory:
    def test_make_from_compact_memory_with_text_content(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        pipeline_inputs: PipelineInputs = {
            "text_item": {
                "concept": NativeConceptCode.TEXT,
                "content": "Hello, world!",
            },
        }

        working_memory = WorkingMemoryFactory.make_from_pipeline_inputs(pipeline_inputs=pipeline_inputs, concept_provider=get_concept_library())

        assert working_memory is not None
        assert "text_item" in working_memory.root

        stuff = working_memory.root["text_item"]
        assert stuff.concept.code == NativeConceptCode.TEXT
        assert isinstance(stuff.content, TextContent)
        assert stuff.content.text == "Hello, world!"

    def test_make_from_compact_memory_with_complex_nested_content(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test deserialization of compact memory with complex nested structured content."""
        pipeline_inputs: PipelineInputs = {
            "complex_page": {
                "concept": NativeConceptCode.PAGE,
                "content": {
                    "text_and_images": {
                        "text": {
                            "text": "This is a complex document page with multiple images and rich text content. "
                            "It demonstrates nested structured content handling.",
                        },
                        "images": [
                            {
                                "url": ImageTestCases.IMAGE_FILE_PATH_JPG_1,
                                "caption": "First image showing data visualization",
                                "source_prompt": "Generate a chart showing quarterly sales data",
                            },
                            {"url": ImageTestCases.IMAGE_FILE_PATH_PNG_2, "caption": "System architecture diagram"},
                        ],
                    },
                    "page_view": {"url": ImageTestCases.IMAGE_FILE_PATH_PNG_3, "caption": "Full page screenshot"},
                },
            },
        }

        working_memory = WorkingMemoryFactory.make_from_pipeline_inputs(pipeline_inputs=pipeline_inputs, concept_provider=get_concept_library())

        assert working_memory is not None
        assert "complex_page" in working_memory.root

        stuff = working_memory.root["complex_page"]
        assert stuff.concept.code == NativeConceptCode.PAGE
        assert isinstance(stuff.content, PageContent)

        # Verify text_and_images structure
        page_content = stuff.content
        assert isinstance(page_content.text_and_images, TextAndImagesContent)

        # Verify text content
        text_content = page_content.text_and_images.text
        assert text_content is not None
        assert isinstance(text_content, TextContent)
        assert "complex document page" in text_content.text

        # Verify images
        images = page_content.text_and_images.images
        assert images is not None
        assert len(images) == 2

        # Check first image
        first_image = images[0]
        assert isinstance(first_image, ImageContent)
        assert first_image.url == ImageTestCases.IMAGE_FILE_PATH_JPG_1
        assert first_image.caption == "First image showing data visualization"
        assert first_image.source_prompt == "Generate a chart showing quarterly sales data"

        # Check second image
        second_image = images[1]
        assert isinstance(second_image, ImageContent)
        assert second_image.url == ImageTestCases.IMAGE_FILE_PATH_PNG_2
        assert second_image.caption == "System architecture diagram"

        # Verify page_view
        page_view = page_content.page_view
        assert page_view is not None
        assert isinstance(page_view, ImageContent)
        assert page_view.url == ImageTestCases.IMAGE_FILE_PATH_PNG_3
        assert page_view.caption == "Full page screenshot"

    def test_make_from_compact_memory_empty(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test deserialization of empty compact memory."""
        pipeline_inputs: PipelineInputs = {}

        working_memory = WorkingMemoryFactory.make_from_pipeline_inputs(pipeline_inputs=pipeline_inputs, concept_provider=get_concept_library())

        assert working_memory is not None
        assert len(working_memory.root) == 0

    def test_make_from_compact_memory_multiple_items(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test deserialization of compact memory with multiple items."""
        pipeline_inputs: PipelineInputs = {
            "text1": {
                "concept": NativeConceptCode.TEXT,
                "content": "First text",
            },
            "text2": {
                "concept": NativeConceptCode.TEXT,
                "content": "Second text",
            },
        }

        working_memory = WorkingMemoryFactory.make_from_pipeline_inputs(pipeline_inputs=pipeline_inputs, concept_provider=get_concept_library())

        assert working_memory is not None
        assert len(working_memory.root) == 2
        assert "text1" in working_memory.root
        assert "text2" in working_memory.root

        # Verify text content
        text1_stuff = working_memory.root["text1"]
        assert isinstance(text1_stuff.content, TextContent)
        assert text1_stuff.content.text == "First text"

        text2_stuff = working_memory.root["text2"]
        assert isinstance(text2_stuff.content, TextContent)
        assert text2_stuff.content.text == "Second text"

    def test_without_specs_stays_bottom_up(self, load_empty_library: Callable[[], None]):
        """Smart Inputs regression: with no signature (`input_specs=None`), shaping is bypassed and
        the bottom-up behavior is unchanged — a bare string still becomes native.Text.
        """
        load_empty_library()
        # A bare string is narrower than the PipelineInputs alias formally admits, but flows at runtime.
        pipeline_inputs: dict[str, Any] = {"greeting": "hello"}

        working_memory = WorkingMemoryFactory.make_from_pipeline_inputs(
            pipeline_inputs=pipeline_inputs, input_specs=None, concept_provider=get_concept_library()
        )

        stuff = working_memory.root["greeting"]
        assert stuff.concept.code == NativeConceptCode.TEXT
        assert isinstance(stuff.content, TextContent)
        assert stuff.content.text == "hello"

    def test_with_specs_shapes_bare_int_to_declared_number(self, load_empty_library: Callable[[], None]):
        """A bare int reaches the shaper at runtime despite the narrow PipelineInputs alias (D10 is
        release-gated) and is typed as the declared Number concept — the seam's runtime-reachability pin.
        """
        load_empty_library()
        number_concept = get_native_concept(native_concept=NativeConceptCode.NUMBER)
        input_specs = InputStuffSpecs(root={"count": StuffSpec(concept=number_concept)})
        pipeline_inputs: dict[str, Any] = {"count": 42}

        working_memory = WorkingMemoryFactory.make_from_pipeline_inputs(
            pipeline_inputs=pipeline_inputs, input_specs=input_specs, concept_provider=get_concept_library()
        )

        stuff = working_memory.root["count"]
        assert stuff.concept.code == NativeConceptCode.NUMBER
        assert isinstance(stuff.content, NumberContent)
        assert stuff.content.number == 42
