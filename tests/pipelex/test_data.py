# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, ClassVar, List, Optional, Tuple

from pydantic import BaseModel
from typing_extensions import override

from pipelex.core.domain import SpecialDomain
from pipelex.core.pipe_run_params import PipeOutputMultiplicity
from pipelex.core.stuff import Stuff
from pipelex.core.stuff_content import ImageContent, ListContent, TextContent
from pipelex.core.stuff_factory import StuffBlueprint, StuffFactory
from pipelex.tools.templating.templating_models import PromptingStyle, TagStyle, TextFormat


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
    IMGG_PROMPT = "dog playing chess"
    URL_IMG_GANTT_1 = "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/diagrams/gantt_tree_house.png"  # AI generated
    URL_IMG_INVOICE_1 = "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/invoices/invoice_1.png"  # AI generated
    URL_IMG_FASHION_PHOTO_1 = "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/fashion/fashion_photo_1.jpg"  # AI generated
    URL_IMG_AD_BANNER_1 = "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/marketing/ad_banner_1.png"  # AI generated
    PATH_TEXT_FILE_1 = "tests/pipelex/data/texts/text_1.txt"

    # Create simple Stuff objects
    SIMPLE_STUFF_TEXT = StuffFactory.make_stuff(
        name="text",
        concept_code="native.Text",
        content=TextContent(text="Describe a t-shirt in 2 sentences"),
        pipelex_session_id="unit_test",
    )
    SIMPLE_STUFF_IMAGE = StuffFactory.make_stuff(
        name="image",
        concept_code="native.Image",
        content=ImageContent(url=URL_IMG_FASHION_PHOTO_1),
        pipelex_session_id="unit_test",
    )
    COMPLEX_STUFF = StuffFactory.make_stuff(
        name="complex",
        concept_code="tests.Complex",
        content=ListContent(
            items=[
                TextContent(text="The quick brown fox jumps over the lazy dog"),
                ImageContent(url=URL_IMG_GANTT_1),
            ]
        ),
        pipelex_session_id="unit_test",
    )

    TRICKY_QUESTION_BLUEPRINT_1 = StuffBlueprint(name="question", concept="answer.Question", value=USER_TEXT_TRICKY_1)
    TRICKY_QUESTION_BLUEPRINT_2 = StuffBlueprint(name="question", concept="answer.Question", value=USER_TEXT_TRICKY_2)
    IMG_BLUEPRINT = StuffBlueprint(name="image", concept=f"{SpecialDomain.NATIVE}.Image", value=URL_IMG_GANTT_1)
    EXPENSE_REPORT_BLUEPRINT_1 = StuffBlueprint(name="invoice_image", concept="invoice.InvoiceImage", value=URL_IMG_INVOICE_1)
    BLUEPRINT_OBJ: ClassVar[List[Tuple[str, StuffBlueprint]]] = [  # topic, blueprint
        (
            "Tricky",
            TRICKY_QUESTION_BLUEPRINT_1,
        ),
    ]
    BAD_MISSION_TO_TEST_FAIULRE: ClassVar[List[Tuple[str, str, str]]] = [  # topic, source_text, sequence_str
        (
            "Bad sequence",
            USER_TEXT_TRICKY_1,
            "foo-bar",
        ),
    ]
    TEXT_MISSION: ClassVar[List[Tuple[str, str, str]]] = [  # topic, source_text, sequence_str
        (
            "Describe an image",
            URL_IMG_GANTT_1,
            "Image-VisualDescription",
        ),
        (
            "Conclude",
            USER_TEXT_TRICKY_1,
            "Question-ThoughtfulAnswerConclusion",
        ),
    ]
    BLUEPRINT_AND_PIPE: ClassVar[List[Tuple[str, StuffBlueprint, str]]] = [  # topic, blueprint, pipe
        (
            "Tricky question conclude",
            TRICKY_QUESTION_BLUEPRINT_2,
            "conclude_tricky_question_by_steps",
        ),
    ]
    NO_INPUT: ClassVar[List[Tuple[str, str]]] = [  # topic, pipe
        (
            "Test with no input",
            "test_no_input",
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
    NO_INPUT_MULTIPLE: ClassVar[List[Tuple[str, str, str]]] = [  # topic, pipe, _output_concept
        (
            "Pick and choose",
            "pick_and_choose",
            "flows.Color",
        ),
    ]
    NO_INPUT_PARALLEL: ClassVar[List[Tuple[str, str, int]]] = [  # topic, pipe, multiplicity
        (
            "Nature colors painting",
            "imagine_nature_product_list",
            5,
        ),
    ]

    BATCH_TEST: ClassVar[List[Tuple[str, Stuff, str, str]]] = [  # pipe_code, stuff, input_list_stuff_name, input_item_stuff_name
        (
            "batch_test",
            StuffFactory.make_stuff(
                concept_code="flows.Color",
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
    SIMPLE_PIPE_RUN_FROM_STR: ClassVar[List[Tuple[str, str, str]]] = [  # pipe_code, input_concept_code, str_value
        (
            "extract_colors",
            "native.Text",
            USER_TEXT_COLORS,
        ),
    ]


class ContractTest:
    PROJECT_CONTEXT = """
        We are working on contracts for a Macdonald franchise.
        We use a Contract Lifecycle Management (CLM) Platform.
        To efficiently manage our contracts, we need to extract the key terms from these contracts.
    """
    CONTRACT_TEST_CASES: ClassVar[List[str]] = [  # question
        "Contract Type",
        "Fees",
        "Governing Law",
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
    BLUEPRINT: ClassVar[List[StuffBlueprint]] = [
        PipeTestCases.TRICKY_QUESTION_BLUEPRINT_1,
    ]
    STUFF: ClassVar[List[Tuple[str, Stuff]]] = [
        ("cherry", PipeTestCases.SIMPLE_STUFF_TEXT),
        ("complex", PipeTestCases.COMPLEX_STUFF),
    ]
    ANY_OBJECT: ClassVar[List[Tuple[str, Any]]] = [
        ("cherry", PipeTestCases.SIMPLE_STUFF_TEXT),
        ("complex", PipeTestCases.COMPLEX_STUFF),
    ]


class FormatAnswerTestCases:
    QUESTION = "What is 3 * 9?"
    QUESTION_WITH_EXCERPT = "How many points for the winning side?"
    EXCERPT = (
        "After a huge loss at the Saints, the Colts traveled to Nashville take on the Titans. "
        "The Titans would score 20 unanswered points in the 1st half alone as Rob Bironas would kick "
        "a 51-yard field goal for a 3-0 lead in the first quarter. In the 2nd quarter, Jason McCourty "
        "would recover a blocked punt in the end zone sending the game to 10-0, followed up by Bironas "
        "nailing a 50-yard field goal for 13-0 and eventual halftime lead of 20-0 when Nate Washington "
        "ran for a 3-yard touchdown. The Colts would manage to get on the board as Adam Vinatieri would "
        "kick a 22-yard field goal for a 20-3 lead. Donald Brown managed to increase his team's points "
        "with a 4-yard touchdown run for a 20-10 lead. The Titans however wrapped the game up when "
        "Washington ran for a 14-yard touchdown for a final score of 27-10. With the loss, the Colts "
        "fell to 0-8."
    )


class LibraryTestCases:
    KNOWN_CONCEPTS_AND_PIPES: ClassVar[List[Tuple[str, str]]] = [  # concept, pipe
        ("cars.CarDescription", "generate_car_description"),
        # ("animals.AnimalDescription", "generate_animal_description"),
        # ("gpu.GPUDescription", "generate_gpu_description"),
    ]


class PipeOCRTestCases:
    PIPE_OCR_TEST_CASES: ClassVar[List[Tuple[Optional[str], Optional[str]]]] = [  # image_file_path, pdf_url
        ("tests/cogt/data/documents/solar_system.png", None),
        (None, "tests/cogt/data/documents/solar_system.pdf"),
        ("https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/documents/solar_system.png", None),
        (None, "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/documents/solar_system.pdf"),
    ]
