from typing import Any, ClassVar, List, Optional, Tuple, Type

from pydantic import BaseModel
from typing_extensions import override

from pipelex.core.pipe_run_params import PipeOutputMultiplicity
from pipelex.core.stuff import Stuff
from pipelex.core.stuff_content import ImageContent, ListContent, PDFContent, StructuredContent, TextContent
from pipelex.core.stuff_factory import StuffBlueprint, StuffFactory
from pipelex.exceptions import PipeStackOverflowError
from pipelex.tools.templating.templating_models import PromptingStyle, TagStyle, TextFormat
from tests.test_data import ImageTestCases, PDFTestCases


class SomeContentWithImageAttribute(StructuredContent):
    image_attribute: ImageContent


class SomeContentWithImageSubObjectAttribute(StructuredContent):
    image_attribute: ImageContent
    sub_object: Optional["SomeContentWithImageAttribute"] = None


class PipeTestCases:
    SYSTEM_PROMPT = "You are a pirate, you always talk like a pirate."
    USER_PROMPT = "In 3 sentences, tell me about the sea."
    USER_TEXT_TRICKY_1 = """
        When my son was 7 he was 3ft tall. When he was 8 he was 4ft tall. When he was 9 he was 5ft tall.
        How tall do you think he was when he was 12? and at 15?
    """
    USER_TEXT_TRICKY_2 = """
        A man, a cabbage, and a goat are trying to cross a river.
        They have a boat that can only carry three things at once. How do they do it?
    """
    USER_TEXT_COLORS = """
        The sky is blue.
        The grass is green.
        The sun is yellow.
        The moon is white.
    """
    MULTI_IMG_DESC_PROMPT = "If there is one image, describe it. If there are multiple images, compare them."
    URL_IMG_GANTT_1 = "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/diagrams/gantt_tree_house.png"  # AI generated
    URL_IMG_FASHION_PHOTO_1 = "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/fashion/fashion_photo_1.jpg"  # AI generated
    URL_IMG_FASHION_PHOTO_2 = "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/fashion/fashion_photo_2.png"  # AI generated

    # Create simple Stuff objects
    SIMPLE_STUFF_TEXT = StuffFactory.make_stuff(
        name="text",
        concept_str="Text",
        content=TextContent(text="Describe a t-shirt in 2 sentences"),
        pipelex_session_id="unit_test",
    )
    SIMPLE_STUFF_IMAGE = StuffFactory.make_stuff(
        name="image",
        concept_str="Image",
        content=ImageContent(url=URL_IMG_FASHION_PHOTO_1),
        pipelex_session_id="unit_test",
    )
    SIMPLE_STUFF_PDF = StuffFactory.make_stuff(
        name="pdf",
        concept_str="PDF",
        content=PDFContent(url=PDFTestCases.DOCUMENT_URLS[0]),
        pipelex_session_id="unit_test",
    )
    COMPLEX_STUFF = StuffFactory.make_stuff(
        name="complex",
        concept_str="tests.Complex",
        content=ListContent(
            items=[
                TextContent(text="The quick brown fox jumps over the lazy dog"),
                ImageContent(url=URL_IMG_GANTT_1),
            ]
        ),
        pipelex_session_id="unit_test",
    )

    STUFF_CONTENT_WITH_IMAGE_ATTRIBUTE_1 = SomeContentWithImageAttribute(image_attribute=ImageContent(url=URL_IMG_FASHION_PHOTO_1))
    STUFF_WITH_IMAGE_ATTRIBUTE = StuffFactory.make_stuff(
        concept_str="Image",
        content=STUFF_CONTENT_WITH_IMAGE_ATTRIBUTE_1,
        name="stuff_with_image",
        pipelex_session_id="unit_test",
    )
    STUFF_CONTENT_WITH_IMAGE_ATTRIBUTE_IN_SUB_OBJECT = SomeContentWithImageSubObjectAttribute(
        image_attribute=ImageContent(url=URL_IMG_FASHION_PHOTO_2),
        sub_object=STUFF_CONTENT_WITH_IMAGE_ATTRIBUTE_1,
    )
    STUFF_WITH_IMAGE_ATTRIBUTE_IN_SUB_OBJECT = StuffFactory.make_stuff(
        concept_str="Image",
        content=STUFF_CONTENT_WITH_IMAGE_ATTRIBUTE_IN_SUB_OBJECT,
        name="stuff_with_image_in_sub_object",
        pipelex_session_id="unit_test",
    )
    STUFFS_IMAGE_ATTRIBUTES: ClassVar[List[Tuple[Stuff, List[str]]]] = [  # stuff, attribute_paths
        (STUFF_WITH_IMAGE_ATTRIBUTE, ["stuff_with_image.image_attribute"]),
        (STUFF_WITH_IMAGE_ATTRIBUTE_IN_SUB_OBJECT, ["stuff_with_image_in_sub_object.image_attribute"]),
        (STUFF_WITH_IMAGE_ATTRIBUTE_IN_SUB_OBJECT, ["stuff_with_image_in_sub_object.sub_object.image_attribute"]),
        (
            STUFF_WITH_IMAGE_ATTRIBUTE_IN_SUB_OBJECT,
            [
                "stuff_with_image_in_sub_object.image_attribute",
                "stuff_with_image_in_sub_object.sub_object.image_attribute",
            ],
        ),
    ]
    TRICKY_QUESTION_BLUEPRINT = StuffBlueprint(name="question", concept="answer.Question", value=USER_TEXT_TRICKY_2)
    BLUEPRINT_AND_PIPE: ClassVar[List[Tuple[str, StuffBlueprint, str]]] = [  # topic, blueprint, pipe
        (
            "Tricky question conclude",
            TRICKY_QUESTION_BLUEPRINT,
            "conclude_tricky_question_by_steps",
        ),
    ]
    NO_INPUT: ClassVar[List[Tuple[str, str]]] = [  # topic, pipe
        (
            "Test with no input",
            "test_no_input",
        ),
        (
            "Test with no input that could be long",
            "test_no_input_that_could_be_long",
        ),
    ]
    NO_INPUT_PARALLEL1: ClassVar[List[Tuple[str, str, Optional[PipeOutputMultiplicity]]]] = [  # topic, pipe, multiplicity
        (
            "Nature colors painting",
            "choose_colors",
            5,
        ),
        (
            "Power Rangers colors",
            "imagine_nature_scene_of_original_power_rangers_colors",
            None,
        ),
        (
            "Power Rangers colors",
            "imagine_nature_scene_of_alltime_power_rangers_colors",
            True,
        ),
    ]

    BATCH_TEST: ClassVar[List[Tuple[str, Stuff, str, str]]] = [  # pipe_code, stuff, input_list_stuff_name, input_item_stuff_name
        (
            "batch_test",
            StuffFactory.make_stuff(
                concept_str="flows.Color",
                name="colors",
                content=ListContent(
                    items=[
                        TextContent(text="blue"),
                        TextContent(text="red"),
                        TextContent(text="green"),
                    ]
                ),
                pipelex_session_id="unit_test",
            ),
            "colors",
            "color",
        ),
    ]
    STUFF_AND_PIPE: ClassVar[List[Tuple[str, Stuff, str]]] = [  # topic, stuff, pipe_code
        (
            "Process Simple Image",
            SIMPLE_STUFF_IMAGE,
            "simple_llm_test_from_image",
        ),
        (
            "Extract page contents from PDF",
            SIMPLE_STUFF_PDF,
            "extract_page_contents_from_pdf",
        ),
    ]
    FAILURE_PIPES: ClassVar[List[Tuple[str, Type[Exception], str]]] = [
        (
            "infinite_loop_1",
            PipeStackOverflowError,
            "Exceeded pipe stack limit",
        ),
    ]


class Fruit(BaseModel):
    name: str
    color: str

    @override
    def __str__(self) -> str:
        return self.name


class JINJA2TestCases:
    JINJA2_NAME: ClassVar[List[str]] = [
        "jinja2_test_template",
    ]
    JINJA2_FOR_ANY: ClassVar[List[str]] = [
        "I want a {{ place_holder }} cocktail.",
    ]
    JINJA2_FILTER_TAG = """
Tag filter:
{{ place_holder | tag("some stuff") }}
"""
    JINJA2_FILTER_FORMAT = """
Format filter:
{{ place_holder | format }}
"""
    JINJA2_FILTER_FORMAT_PLAIN = """
Format filter plain:
{{ place_holder | format("plain") }}
"""
    JINJA2_FILTER_FORMAT_JSON = """
Format filter json:
{{ place_holder | format("json") }}
"""
    JINJA2_FILTER_FORMAT_MARKDOWN = """
Format filter markdown:
{{ place_holder | format("markdown") }}
"""
    JINJA2_FILTER_FORMAT_HTML = """
Format filter html:
{{ place_holder | format("html") }}
"""
    JINJA2_FILTER_FORMAT_SPREADSHEET = """
Format filter spreadsheet:
{{ place_holder | format("spreadsheet") }}
"""
    JINJA2_ALL_METHODS = """
Direct (no filter):
{{ place_holder }}

Format filter:
{{ place_holder | format }}

Tag filter:
{{ place_holder | tag("some stuff") }}

Format filter json:
{{ place_holder | format("json") }}

Format filter markdown:
{{ place_holder | format("markdown") }}

Format filter html:
{{ place_holder | format("html") }}

"""
    JINJA2_FOR_STUFF: ClassVar[List[str]] = [
        JINJA2_FILTER_TAG,
        JINJA2_FILTER_FORMAT,
        JINJA2_FILTER_FORMAT_PLAIN,
        JINJA2_FILTER_FORMAT_JSON,
        JINJA2_FILTER_FORMAT_MARKDOWN,
        JINJA2_FILTER_FORMAT_HTML,
        JINJA2_FILTER_FORMAT_SPREADSHEET,
        JINJA2_ALL_METHODS,
    ]
    STYLE: ClassVar[List[PromptingStyle]] = [
        PromptingStyle(
            tag_style=TagStyle.NO_TAG,
            text_format=TextFormat.PLAIN,
        ),
        PromptingStyle(
            tag_style=TagStyle.TICKS,
            text_format=TextFormat.MARKDOWN,
        ),
        PromptingStyle(
            tag_style=TagStyle.XML,
            text_format=TextFormat.HTML,
        ),
        PromptingStyle(
            tag_style=TagStyle.SQUARE_BRACKETS,
            text_format=TextFormat.JSON,
        ),
    ]
    COLOR: ClassVar[List[str]] = [
        "red",
        "blue",
        "green",
    ]
    FRUIT: ClassVar[List[Fruit]] = [
        (Fruit(color="red", name="cherry")),
        (Fruit(color="blue", name="blueberry")),
        (Fruit(color="green", name="grape")),
    ]
    ANY_OBJECT: ClassVar[List[Tuple[str, Any]]] = [
        ("cherry", PipeTestCases.SIMPLE_STUFF_TEXT),
        # ("complex", PipeTestCases.COMPLEX_STUFF),
    ]


class LibraryTestCases:
    KNOWN_CONCEPTS_AND_PIPES: ClassVar[List[Tuple[str, str]]] = [  # concept, pipe
        ("cars.CarDescription", "generate_car_description"),
        ("animals.AnimalDescription", "generate_animal_description"),
        ("flowers.FlowerDescription", "generate_flower_description"),
    ]


class PipeOcrTestCases:
    PIPE_OCR_IMAGE_TEST_CASES: ClassVar[List[str]] = [
        ImageTestCases.IMAGE_FILE_PATH_PNG,
        ImageTestCases.IMAGE_URL_PNG,
    ]
    PIPE_OCR_PDF_TEST_CASES: ClassVar[List[str]] = PDFTestCases.DOCUMENT_FILE_PATHS + PDFTestCases.DOCUMENT_URLS


class IMGGTestCases:
    IMGG_PROMPT_1 = "woman wearing marino cargo pants"
    IMGG_PROMPT_2 = "wide legged denim pants with hippy addition"
    IMGG_PROMPT_3 = """
Woman typing on a laptop. On the laptop screen you see python code to generate code to write a prompt for an AI model.
"""

    IMAGE_DESC: ClassVar[List[Tuple[str, str]]] = [  # topic, imgg_prompt_text
        # (IMGG_PROMPT_1, IMGG_PROMPT_1),
        # (IMGG_PROMPT_2, IMGG_PROMPT_2),
        # (IMGG_PROMPT_3, IMGG_PROMPT_3),
        ("coding girl", "a girl with a dragon tatoo, coding in python"),
    ]
