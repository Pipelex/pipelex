from typing import ClassVar

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent


class PipeTestCases:
    SYSTEM_PROMPT = "You are a pirate, you always talk like a pirate."
    USER_PROMPT = "In 3 sentences, tell me about the sea."
    USER_TEXT_TRICKY_1 = """
        When my son was 7 he was 3ft tall. When he was 8 he was 4ft tall. When he was 9 he was 5ft tall.
        How tall do you think he was when he was 12? and at 15?
        """

    # Create simple Stuff objects
    SIMPLE_STUFF = StuffFactory.make_stuff(
        name="text",
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
        content=TextContent(text="Describe a t-shirt in 2 sentences"),
    )

    IMG_EXPENSE_REPORT_1 = "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/invoices/invoice_1.png"
    IMG_FASHION_PHOTO_1 = "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/fashion/fashion_photo_1.jpg"
    SIMPLE_STUFF_TEXT = StuffFactory.make_stuff(
        name="text",
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
        content=TextContent(text="Describe a t-shirt in 2 sentences"),
    )
    SIMPLE_STUFF_IMAGE = StuffFactory.make_stuff(
        name="image",
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
        content=ImageContent(url=IMG_FASHION_PHOTO_1),
    )

    BATCH_TEST: ClassVar[list[tuple[str, Stuff, str, str]]] = [  # pipe_code, stuff, input_list_stuff_name, input_item_stuff_name
        (
            "batch_test",
            StuffFactory.make_stuff(
                concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
                name="colors",
                content=ListContent(
                    items=[
                        TextContent(text="blue"),
                        TextContent(text="red"),
                        TextContent(text="green"),
                    ]
                ),
            ),
            "colors",
            "color",
        ),
    ]
    STUFF_AND_PIPE: ClassVar[list[tuple[str, Stuff, str]]] = [  # topic, stuff, pipe_code
        # TODO: fix testing implict concept
        # (
        #     "Process Simple Text",
        #     SIMPLE_STUFF,
        #     "test_implicit_concept",
        # ),
        # (
        #     "Process Simple Text",
        #     SIMPLE_STUFF_TEXT,
        #     "simple_llm_test_from_text",
        # ),
        (
            "Process Simple Image",
            SIMPLE_STUFF_IMAGE,
            "simple_llm_test_from_image",
        ),
    ]

    NO_INPUT: ClassVar[list[tuple[str, str]]] = [  # topic, pipe
        (
            "Test with no input",
            "test_no_input",
        ),
        (
            "Imagine nature products of different colors",
            "imagine_nature_product_list",
        ),
        (
            "Create characters",
            "create_characters",
        ),
    ]


class LibraryCrateTestData:
    """Test constants for LibraryCrate integration tests.

    Uses a PipeSequence bundle with only native Text concepts (no dynamic classes)
    to avoid the Layer 1 Kajson deserialization issue (Phase 3). This still fully
    tests Layer 2 (pipe resolution via get_required_pipe on the worker).
    """

    BUNDLE_DIR: ClassVar[str] = "tests/integration/pipelex/temporal/async/library_crate"
    BUNDLE_FILE: ClassVar[str] = "tests/integration/pipelex/temporal/async/library_crate/native_text_sequence.mthds"
    PIPE_CODE: ClassVar[str] = "native_text_sequence"
    DOMAIN: ClassVar[str] = "native_text_test"

    EXPECTED_PIPE_REFS: ClassVar[list[str]] = [
        "native_text_test.native_text_sequence",
        "native_text_test.step_one",
        "native_text_test.step_two",
    ]


class PipeOcrTestCases:
    PIPE_OCR_IMAGE_TEST_CASES: ClassVar[list[str]] = [
        # LOCAL
        "tests/data/documents/solar_system.png",
        # REMOTE
        "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/documents/solar_system.png",
    ]
    PIPE_OCR_PDF_TEST_CASES: ClassVar[list[str]] = [
        # LOCAL
        "tests/data/documents/solar_system.pdf",
        # REMOTE
        "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/documents/solar_system.pdf",
    ]
