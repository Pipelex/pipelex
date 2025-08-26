from typing import ClassVar, List, Optional, Tuple, Type

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NATIVE_CONCEPTS_DATA, NativeConceptEnum
from pipelex.core.pipes.pipe_run_params import PipeOutputMultiplicity
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import (
    ImageContent,
    ListContent,
    PDFContent,
    StructuredContent,
    TextContent,
)
from pipelex.core.stuffs.stuff_factory import StuffBlueprint, StuffFactory
from pipelex.exceptions import PipeStackOverflowError
from pipelex.pipe_operators.ocr.pipe_ocr import PIPE_OCR_INPUT_NAME
from tests.cases import ImageTestCases, PDFTestCases


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
        concept=ConceptFactory.make_native_concept(native_concept_data=NATIVE_CONCEPTS_DATA[NativeConceptEnum.TEXT]),
        content=TextContent(text="Describe a t-shirt in 2 sentences"),
    )
    SIMPLE_STUFF_IMAGE = StuffFactory.make_stuff(
        name="image",
        concept=ConceptFactory.make_native_concept(native_concept_data=NATIVE_CONCEPTS_DATA[NativeConceptEnum.IMAGE]),
        content=ImageContent(url=URL_IMG_FASHION_PHOTO_1),
    )
    SIMPLE_STUFF_PDF = StuffFactory.make_stuff(
        name=PIPE_OCR_INPUT_NAME,
        concept=ConceptFactory.make_native_concept(native_concept_data=NATIVE_CONCEPTS_DATA[NativeConceptEnum.PDF]),
        content=PDFContent(url=PDFTestCases.DOCUMENT_URLS[0]),
    )
    COMPLEX_STUFF = StuffFactory.make_stuff(
        name="complex",
        concept=ConceptFactory.make(concept_code="Complex", domain="tests", definition="tests.Complex", structure_class_name="Complex"),
        content=ListContent(
            items=[
                TextContent(text="The quick brown fox jumps over the lazy dog"),
                ImageContent(url=URL_IMG_GANTT_1),
            ]
        ),
    )

    STUFF_CONTENT_WITH_IMAGE_ATTRIBUTE_1 = SomeContentWithImageAttribute(image_attribute=ImageContent(url=URL_IMG_FASHION_PHOTO_1))
    STUFF_WITH_IMAGE_ATTRIBUTE = StuffFactory.make_stuff(
        concept=ConceptFactory.make_native_concept(native_concept_data=NATIVE_CONCEPTS_DATA[NativeConceptEnum.IMAGE]),
        content=STUFF_CONTENT_WITH_IMAGE_ATTRIBUTE_1,
        name="stuff_with_image",
    )
    STUFF_CONTENT_WITH_IMAGE_ATTRIBUTE_IN_SUB_OBJECT = SomeContentWithImageSubObjectAttribute(
        image_attribute=ImageContent(url=URL_IMG_FASHION_PHOTO_2),
        sub_object=STUFF_CONTENT_WITH_IMAGE_ATTRIBUTE_1,
    )
    STUFF_WITH_IMAGE_ATTRIBUTE_IN_SUB_OBJECT = StuffFactory.make_stuff(
        concept=ConceptFactory.make_native_concept(native_concept_data=NATIVE_CONCEPTS_DATA[NativeConceptEnum.IMAGE]),
        content=STUFF_CONTENT_WITH_IMAGE_ATTRIBUTE_IN_SUB_OBJECT,
        name="stuff_with_image_in_sub_object",
    )
    STUFFS_IMAGE_ATTRIBUTES: ClassVar[List[Tuple[Stuff, List[str]]]] = [  # stuff, attribute_paths
        (STUFF_WITH_IMAGE_ATTRIBUTE, ["stuff_with_image.image_attribute"]),
        (
            STUFF_WITH_IMAGE_ATTRIBUTE_IN_SUB_OBJECT,
            ["stuff_with_image_in_sub_object.image_attribute"],
        ),
        (
            STUFF_WITH_IMAGE_ATTRIBUTE_IN_SUB_OBJECT,
            ["stuff_with_image_in_sub_object.sub_object.image_attribute"],
        ),
        (
            STUFF_WITH_IMAGE_ATTRIBUTE_IN_SUB_OBJECT,
            [
                "stuff_with_image_in_sub_object.image_attribute",
                "stuff_with_image_in_sub_object.sub_object.image_attribute",
            ],
        ),
    ]
    TRICKY_QUESTION_BLUEPRINT = StuffBlueprint(
        stuff_name="question",
        concept_string="answer.Question",
        content=USER_TEXT_TRICKY_2,
    )
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

    STUFF_AND_PIPE: ClassVar[List[Tuple[str, Stuff, str]]] = [  # topic, stuff, pipe_code
        (
            "Process Simple Image",
            SIMPLE_STUFF_IMAGE,
            "simple_llm_test_from_image",
        ),
        (
            "Extract page contents from PDF",
            SIMPLE_STUFF_PDF,
            "ocr_page_contents_from_pdf",
        ),
    ]
    FAILURE_PIPES: ClassVar[List[Tuple[str, Type[Exception], str]]] = [
        (
            "infinite_loop_1",
            PipeStackOverflowError,
            "Exceeded pipe stack limit",
        ),
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
