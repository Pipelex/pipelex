from typing import ClassVar, Optional

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
    sub_object: SomeContentWithImageAttribute | None = None


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
            ],
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
    STUFFS_IMAGE_ATTRIBUTES: ClassVar[list[tuple[Stuff, list[str]]]] = [  # stuff, attribute_paths
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
    BLUEPRINT_AND_PIPE: ClassVar[list[tuple[str, StuffBlueprint, str]]] = [  # topic, blueprint, pipe
        (
            "Tricky question conclude",
            TRICKY_QUESTION_BLUEPRINT,
            "conclude_tricky_question_by_steps",
        ),
    ]
    NO_INPUT: ClassVar[list[tuple[str, str]]] = [  # topic, pipe
        (
            "Test with no input",
            "test_no_input",
        ),
        (
            "Test with no input that could be long",
            "test_no_input_that_could_be_long",
        ),
    ]
    NO_INPUT_PARALLEL1: ClassVar[list[tuple[str, str, PipeOutputMultiplicity | None]]] = [  # topic, pipe, multiplicity
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

    STUFF_AND_PIPE: ClassVar[list[tuple[str, Stuff, str]]] = [  # topic, stuff, pipe_code
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
    FAILURE_PIPES: ClassVar[list[tuple[str, type[Exception], str]]] = [
        (
            "infinite_loop_1",
            PipeStackOverflowError,
            "Exceeded pipe stack limit",
        ),
    ]


class LibraryTestCases:
    KNOWN_CONCEPTS_AND_PIPES: ClassVar[list[tuple[str, str]]] = [  # concept, pipe
        ("cars.CarDescription", "generate_car_description"),
        ("animals.AnimalDescription", "generate_animal_description"),
        ("flowers.FlowerDescription", "generate_flower_description"),
    ]


class PipeOcrTestCases:
    PIPE_OCR_IMAGE_TEST_CASES: ClassVar[list[str]] = [
        ImageTestCases.IMAGE_FILE_PATH_PNG,
        ImageTestCases.IMAGE_URL_PNG,
    ]
    PIPE_OCR_PDF_TEST_CASES: ClassVar[list[str]] = PDFTestCases.DOCUMENT_FILE_PATHS + PDFTestCases.DOCUMENT_URLS


class ImageGenTestCases:
    IMG_GEN_PROMPT_1 = "woman wearing marino cargo pants"
    IMG_GEN_PROMPT_2 = "wide legged denim pants with hippy addition"
    IMG_GEN_PROMPT_3 = """
Woman typing on a laptop. On the laptop screen you see python code to generate code to write a prompt for an AI model.
"""

    IMAGE_DESC: ClassVar[list[tuple[str, str]]] = [  # topic, img_gen_prompt_text
        # (IMG_GEN_PROMPT_1, IMG_GEN_PROMPT_1),
        # (IMG_GEN_PROMPT_2, IMG_GEN_PROMPT_2),
        # (IMG_GEN_PROMPT_3, IMG_GEN_PROMPT_3),
        ("coding girl with dragon tatoo", "a girl with a dragon tatoo, coding in python"),
    ]


class BasicStructuredDataTestCases:
    """Test cases for extracting basic structured data without union types."""

    EXTRACTION_PROMPT = """
Extract information from the following text:
@data
"""

    # ConceptWithSimpleStructure test cases
    SIMPLE_STRUCTURE_1 = """
    - name: "Alice Johnson"
    - age: 28
    - is_active: true
    """

    SIMPLE_STRUCTURE_2 = """
    The person's name is Bob Smith, they are 45 years old and their account is not active (is_active: false).
    """

    # ConceptWithOptionals test cases
    OPTIONAL_ALL_PRESENT = """
    - required_field: "This is required"
    - optional_string: "This optional has a value"
    - optional_number: 42
    - optional_date: "2024-03-15T10:30:00"
    """

    OPTIONAL_SOME_MISSING = """
    - required_field: "Only required field present"
    - optional_string: NOT PROVIDED (should be null)
    - optional_number: 100
    - optional_date: NOT PROVIDED (should be null)
    """

    OPTIONAL_ALL_MISSING = """
    - required_field: "Mandatory value here"
    Note: All optional fields should be null/None as they are not provided.
    """

    # ConceptWithLists test cases
    LISTS_WITH_DATA = """
    - string_list: ["apple", "banana", "cherry", "date"]
    - number_list: [1, 2, 3, 5, 8, 13]
    - optional_list: ["first", "second", "third"]
    """

    LISTS_EMPTY = """
    - string_list: [] (empty list)
    - number_list: [] (empty list)
    - optional_list: null (not provided, should be None)
    """

    LISTS_MIXED = """
    - string_list: ["only", "one"]
    - number_list: [42]
    - optional_list: NOT PROVIDED (should be null)
    """

    # ConceptWithNestedStructures test cases
    NESTED_FULL = """
    - simple_nested: {
        name: "Nested Person",
        age: 30,
        is_active: true
      }
    - optional_nested: {
        required_field: "Nested required",
        optional_string: "Has value",
        optional_number: 55,
        optional_date: "2024-01-20T14:00:00"
      }
    - list_of_nested: [
        {name: "First", age: 20, is_active: true},
        {name: "Second", age: 25, is_active: false}
      ]
    """

    NESTED_PARTIAL = """
    - simple_nested: {
        name: "Main Structure",
        age: 40,
        is_active: false
      }
    - optional_nested: NOT PROVIDED (should be None)
    - list_of_nested: [] (empty list)
    """

    NESTED_COMPLEX = """
    - simple_nested: {
        name: "Complex Example",
        age: 35,
        is_active: true
      }
    - optional_nested: {
        required_field: "Required in optional",
        optional_string: null,
        optional_number: null,
        optional_date: "2024-12-01T09:30:00"
      }
    - list_of_nested: [
        {name: "Solo Entry", age: 50, is_active: true}
      ]
    """

    # Combined test cases for parametrized tests
    STRUCTURE_TEST_CASES: ClassVar[list[tuple[str, str, str]]] = [  # topic, data, concept
        ("Simple structure basic", SIMPLE_STRUCTURE_1, "ConceptWithSimpleStructure"),
        ("Simple structure narrative", SIMPLE_STRUCTURE_2, "ConceptWithSimpleStructure"),
        ("Optionals all present", OPTIONAL_ALL_PRESENT, "ConceptWithOptionals"),
        ("Optionals some missing", OPTIONAL_SOME_MISSING, "ConceptWithOptionals"),
        ("Optionals all missing", OPTIONAL_ALL_MISSING, "ConceptWithOptionals"),
        ("Lists with data", LISTS_WITH_DATA, "ConceptWithLists"),
        ("Lists empty", LISTS_EMPTY, "ConceptWithLists"),
        ("Lists mixed", LISTS_MIXED, "ConceptWithLists"),
        ("Nested full", NESTED_FULL, "ConceptWithNestedStructures"),
        ("Nested partial", NESTED_PARTIAL, "ConceptWithNestedStructures"),
        ("Nested complex", NESTED_COMPLEX, "ConceptWithNestedStructures"),
    ]


class ComplexStructuredDataTestCases:
    """Test cases for extracting structured data with complex types (unions, dicts, etc.)."""

    EXTRACTION_PROMPT = """
Extract information from the following text:
@data
"""

    # ConceptWithDicts test cases
    DICTS_WITH_DATA = """
    - string_dict: {"key1": "value1", "key2": "value2", "name": "test"}
    - number_dict: {"count": 10, "score": 95, "id": 999}
    - optional_dict: {"status": "active", "mode": "production"}
    """

    DICTS_EMPTY = """
    - string_dict: {} (empty dictionary)
    - number_dict: {"total": 100}
    - optional_dict: null (not provided)
    """

    # ConceptWithUnions test cases
    UNIONS_STRING_VARIANT = """
    - string_or_int: "This is a string value"
    - optional_union: "Also a string"
    - list_of_unions: ["text1", "text2", 100, 200, "text3"]
    """

    UNIONS_INT_VARIANT = """
    - string_or_int: 42 (as integer)
    - optional_union: true (as boolean)
    - list_of_unions: [1, 2, 3, 4, 5]
    """

    UNIONS_MIXED = """
    - string_or_int: 999
    - optional_union: NOT PROVIDED (should be None)
    - list_of_unions: ["mixed", 123, "types", 456, "here"]
    """

    # ConceptWithComplexUnions test cases
    COMPLEX_UNIONS_1 = """
    - mixed_dict: {"status": "active", "count": 42, "enabled": true}
    - union_or_list: "single string value"
    - optional_complex_union: {"key1": "value1", "key2": "value2"}
    - number_or_bool: 3.14
    """

    COMPLEX_UNIONS_2 = """
    - mixed_dict: {"name": "test", "score": 100, "passed": false}
    - union_or_list: [10, 20, 30, 40]
    - optional_complex_union: ["item1", "item2", "item3"]
    - number_or_bool: true
    """

    COMPLEX_UNIONS_3 = """
    - mixed_dict: {} (empty dictionary)
    - union_or_list: [] (empty list as list of integers)
    - optional_complex_union: NOT PROVIDED (should be None)
    - number_or_bool: 0
    """

    # ConceptWithNestedUnions test cases
    NESTED_UNIONS_SIMPLE = """
    - simple_or_complex: {
        name: "John Doe",
        age: 25,
        is_active: true
      }
    - list_of_union_structures: []
    - optional_nested_union: null
    """

    NESTED_UNIONS_COMPLEX = """
    - simple_or_complex: {
        required_field: "Complex choice",
        optional_string: "Has a value",
        optional_number: null,
        optional_date: "2024-06-15T10:00:00"
      }
    - list_of_union_structures: [
        {name: "Simple", age: 30, is_active: false},
        {string_or_int: "text", optional_union: true, list_of_unions: [1, 2, 3]}
      ]
    - optional_nested_union: {
        string_or_int: 42,
        optional_union: null,
        list_of_unions: ["a", 1, "b", 2]
      }
    """

    NESTED_UNIONS_MIXED = """
    - simple_or_complex: {
        name: "Test User",
        age: 40,
        is_active: false
      }
    - list_of_union_structures: [
        {string_or_int: 100, optional_union: "string", list_of_unions: []},
        {name: "Another", age: 22, is_active: true}
      ]
    - optional_nested_union: {
        mixed_dict: {"x": 1, "y": "two", "z": false},
        union_or_list: "just a string",
        optional_complex_union: ["list", "of", "strings"],
        number_or_bool: false
      }
    """

    # Combined test cases for parametrized tests
    STRUCTURE_TEST_CASES: ClassVar[list[tuple[str, str, str]]] = [  # topic, data, concept
        ("Dicts with data", DICTS_WITH_DATA, "ConceptWithDicts"),
        ("Dicts empty", DICTS_EMPTY, "ConceptWithDicts"),
        ("Unions string variant", UNIONS_STRING_VARIANT, "ConceptWithUnions"),
        ("Unions int variant", UNIONS_INT_VARIANT, "ConceptWithUnions"),
        ("Unions mixed", UNIONS_MIXED, "ConceptWithUnions"),
        ("Complex unions 1", COMPLEX_UNIONS_1, "ConceptWithComplexUnions"),
        ("Complex unions 2", COMPLEX_UNIONS_2, "ConceptWithComplexUnions"),
        ("Complex unions 3", COMPLEX_UNIONS_3, "ConceptWithComplexUnions"),
        ("Nested unions simple", NESTED_UNIONS_SIMPLE, "ConceptWithNestedUnions"),
        ("Nested unions complex", NESTED_UNIONS_COMPLEX, "ConceptWithNestedUnions"),
        ("Nested unions mixed", NESTED_UNIONS_MIXED, "ConceptWithNestedUnions"),
    ]
