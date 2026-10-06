import datetime
from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator
from pydantic.dataclasses import dataclass

from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.cogt.judgment.judgment_models import ChoiceQuestion, JudgmentKind, JudgmentQuestion, JudgmentState, RatingQuestion, YesNoQuestion
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.core.stuffs.choice_content import ChoiceContent
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.time_content import TimeContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from tests.cases import ImageTestCases
from tests.cases.documents import DocumentTestCases
from tests.integration.pipelex.test_data import PipeTestCases


class Person(BaseModel):
    name: str
    age: int


class Employee(Person):
    job: str = Field(description="Job title, must be lowercase")

    @field_validator("job")
    @classmethod
    def validate_lowercase_job(cls, v: str) -> str:
        if not v.islower():
            msg = "job title must be lowercase"
            raise ValueError(msg)
        return v


class PetSpecies(StrEnum):
    DOG = "dog"
    CAT = "cat"
    BIRD = "bird"
    FISH = "fish"
    HAMSTER = "hamster"


class Pet(BaseModel):
    species: PetSpecies
    name: str


class ImageDescription(BaseModel):
    title: str = Field(description="A short title for the image")
    description: str = Field(description="A detailed description of what is shown in the image")
    time_period: str = Field(description="An estimated date or time period relevant to the image (e.g., '2024', 'Modern era', 'Unknown')")


class LLMVisionTestCases:
    VISION_USER_TEXT = "Describe the provide image in 1-2 concise sentences."
    VISION_IMAGES_COMPARE_PROMPT = "Compare these two images in 2-3 concise bullet points."

    URL_CLOUDFRONT_ALAN_TURING_JPG = "https://d2cinlfp2qnig1.cloudfront.net/tests/alan_turing.jpg"

    TEST_IMAGE_DIRECTORY = "tests/data/images"

    PATH_IMG_PNG_1 = f"{TEST_IMAGE_DIRECTORY}/ai_lympics.png"
    PATH_IMG_JPEG_1 = f"{TEST_IMAGE_DIRECTORY}/ai_lympics.jpg"

    PATH_IMG_PNG_2 = f"{TEST_IMAGE_DIRECTORY}/animal_lympics.png"
    PATH_IMG_JPEG_2 = f"{TEST_IMAGE_DIRECTORY}/animal_lympics.jpg"

    PATH_IMG_PNG_3 = f"{TEST_IMAGE_DIRECTORY}/eiffel_tower.png"
    PATH_IMG_JPEG_3 = f"{TEST_IMAGE_DIRECTORY}/eiffel_tower.jpg"

    PATH_IMG_GANTT_1 = f"{TEST_IMAGE_DIRECTORY}/diagram.png"

    IMAGE_PATHS: ClassVar[list[tuple[str, str]]] = [  # topic, image_path
        # ("Gantt Chart", PATH_IMG_GANTT_1),
        ("AI Lympics PNG", PATH_IMG_PNG_1),
        # ("Animal Lympics PNG", PATH_IMG_PNG_2),
        ("AI Lympics JPEG", PATH_IMG_JPEG_1),
        # ("Eiffel Tower", PATH_IMG_JPEG_3),
        # ("Eiffel Tower", PATH_IMG_PNG_3),
    ]
    IMAGE_PATH_PAIRS: ClassVar[list[tuple[str, tuple[str, str]]]] = [  # topic, image_pair
        ("AI Lympics PNG", (PATH_IMG_PNG_1, PATH_IMG_PNG_2)),
    ]

    IMAGE_URLS: ClassVar[list[tuple[str, str]]] = [  # topic, image_uri
        (
            "Alan Turing",
            URL_CLOUDFRONT_ALAN_TURING_JPG,
        ),
        (
            "Gantt chart",
            PipeTestCases.URL_IMG_GANTT_PNG,
        ),
    ]

    # Data URLs for vision tests (topic, data_url)
    IMAGE_DATA_URLS: ClassVar[list[tuple[str, str]]] = [
        ("Pipelex Logo Tiny", ImageTestCases.LOGO_TINY_PNG_DATA_URL),
    ]


class LLMDocumentTestCases:
    """Test cases for LLM document understanding."""

    DOCUMENT_USER_TEXT = "Summarize this document in 2-3 concise sentences."
    DOCUMENT_USER_TEXT_DETAILED = "What are the key points in this document? List them as bullet points."

    # PDF document paths - universally supported across providers
    PDF_DOCUMENT_PATHS: ClassVar[list[tuple[str, str]]] = [  # topic, document_path
        ("Job Offer PDF", DocumentTestCases.PDF_FILE_PATH_2),
    ]

    # DOCX document paths - limited support (Anthropic supports, Google doesn't)
    DOCX_DOCUMENT_PATHS: ClassVar[list[tuple[str, str]]] = [  # topic, document_path
        ("CV DOCX", DocumentTestCases.DOCX_FILE_PATH_1),
    ]

    # Document URLs - using remote URLs from DocumentTestCases
    DOCUMENT_URLS: ClassVar[list[tuple[str, str]]] = [  # topic, document_url
        ("Job Offer URL", DocumentTestCases.PDF_FILE_URL_1),
    ]


class LLMTestConstants:
    USER_TEXT_SHORT = "In one short sentence, who is Bill Gates?"
    USER_TEXT_SUPER_SHORT = "In one short sentence (< 5 words), who is Bill Gates?"
    USER_TEXT_TO_EXTRACT_PERSON = "It's Robert, the nice plumber, he turns 57 next week."
    USER_TEXT_TO_GEN_PERSON_LIST = "List the following people: Alice is 30, Bob is 25, and Charlie is 35."
    USER_TEXT_TRICKY_1 = """
When my son was 7 he was 3ft tall. When he was 8 he was 4ft tall. When he was 9 he was 5ft tall.
How tall do you think he was when he was 12? and at 15?
"""
    USER_TEXT_TRICKY_2 = """
Count the Rs in "Strawberry"
"""
    # USER_TEXT_SHORT = "What's the biggest football match tonight in Europe?"
    PROMPT_TEMPLATE_TEXT = "Can you give one example of flower which is {color} in color ?"
    PROMPT_COLOR_EXAMPLES: ClassVar[list[str]] = [
        "red",
        "blue",
        "green",
        "yellow",
        "orange",
        "purple",
        "pink",
        "black",
        "white",
    ]


class LLMTestCases:
    USER_TEXT_HAIKU = "Write a sonnet about the sea"
    USER_TEXT_TRICKY = """
When my son was 7 he was 3ft tall. When he was 8 he was 4ft tall. When he was 9 he was 5ft tall.
How tall do you think he was when he was 12? and at 15?
"""
    SINGLE_TEXT: ClassVar[list[tuple[str, str]]] = [  # topic, prompt_text
        ("Haiku", USER_TEXT_HAIKU),
        ("Tricky", USER_TEXT_TRICKY),
    ]
    SINGLE_OBJECT: ClassVar[list[tuple[str, BaseModel]]] = [
        ("name: John, age: 30", Person(name="John", age=30)),
        ("Betty Draper, 51", Person(name="Betty Draper", age=51)),
        ("Whiskers, the cat", Pet(species=PetSpecies.CAT, name="Whiskers")),
        ("Whiskers, the dog", Pet(species=PetSpecies.DOG, name="Whiskers")),
    ]
    MULTIPLE_OBJECTS: ClassVar[list[list[tuple[str, BaseModel]]]] = [
        [
            ("name: John, age: 30", Person(name="John", age=30)),
            # ("Betty Draper, 51", Person(name="Betty Draper", age=51)),
            ("Whiskers, a very nice cat", Pet(species=PetSpecies.CAT, name="Whiskers")),
            ("Whiskers, a cute little dog", Pet(species=PetSpecies.DOG, name="Whiskers")),
        ],
        [
            # ("name: Alice, age: 25", Person(name="Alice", age=25)),
            ("My sister's plumber, Bob Smith, is 42", Employee(name="Bob Smith", age=42, job="plumber")),
            ("Fluffy is a funny hamster", Pet(species=PetSpecies.HAMSTER, name="Fluffy")),
            ("Rex is a big black dog", Pet(species=PetSpecies.DOG, name="Rex")),
        ],
    ]


class SerDeTestLLMCases:
    """Constants and example objects used for SerDe unit tests.

    The subject is `LLMPrompt`, which really does cross a process boundary — the interpreter hands one
    to a worker, and a distributed run serializes it onto the wire. Its `user_images` list is the part
    that matters: the items are `PromptImage` subclasses, so a round-trip that lost the subclass would
    hand the model a prompt with no image and nothing downstream would notice.
    """

    # Base building blocks -------------------------------------------------
    PLAIN_PROMPT: ClassVar[LLMPrompt] = LLMPrompt(
        user_text="Some user text in the prompt",
    )

    PROMPT_WITH_SYSTEM_TEXT: ClassVar[LLMPrompt] = LLMPrompt(
        system_text="Some system text",
        user_text="Some user text in the prompt",
    )

    # Dictionary representation example ------------------------------------
    DICT_1: ClassVar[dict[str, Any]] = {
        "system_text": None,
        "user_text": "Some user text in the prompt",
        "user_images": [],
    }

    # Prompt containing an image URI --------------------------------------
    PROMPT_WITH_IMAGE_URI: ClassVar[LLMPrompt] = LLMPrompt(
        system_text="Some system text",
        user_text="Some user text",
        user_images=[
            PromptImageUri(uri="some_file_path"),
        ],
    )

    # Group constants for parametrization ----------------------------------
    PYDANTIC_EXAMPLES: ClassVar[list[BaseModel]] = [
        PLAIN_PROMPT,
        PROMPT_WITH_SYSTEM_TEXT,
    ]
    PYDANTIC_EXAMPLES_USING_SUBCLASS: ClassVar[list[BaseModel]] = [
        PROMPT_WITH_IMAGE_URI,
    ]
    PYDANTIC_EXAMPLES_DICT: ClassVar[list[dict[str, Any]]] = [
        DICT_1,
    ]


class SearchTestCases:
    """Test cases for search integration tests."""

    SOURCED_ANSWER_QUERIES: ClassVar[list[tuple[str, str]]] = [  # topic, query
        ("Declarative languages", "What makes declarative languages different from imperative languages?"),
        # ("Middle East", "Latest events in the middle east"),
        # ("Capital of France", "What is the capital of France?"),
        # ("Python creator", "Who created the Python programming language?"),
    ]

    STRUCTURED_QUERIES: ClassVar[list[tuple[str, str]]] = [  # topic, query
        ("Middle East", "Latest events in the middle east"),
        # ("Python language", "What is the Python programming language and what are its main features?"),
    ]


class LLMReasoningTestCases:
    """Test cases for LLM reasoning/thinking integration tests."""

    PROMPTS: ClassVar[list[tuple[str, str]]] = [  # topic, prompt_text
        ("Comparison", "Which is larger: 0.9 or 0.11?"),
        ("Letter counting", "How many Rs are in the word 'Strawberry'?"),
        ("Multiplication", "What is 317 * 723?"),
        # ("Huge multiplication", "What is 9738317 * 723837893?"),
        # (
        #     "Tricky growth",
        #     """
        #     When my son was 7 he was 3ft tall. When he was 8 he was 4ft tall. When he was 9 he was 5ft tall.
        #     How tall do you think he was when he was 12? and at 15?
        #     Conclude with your opinion as a one-sentence answer.
        # """,
        # ),
        # (
        #     "Tricky river crossing",
        #     """
        #     A man, a cabbage, and a goat are trying to cross a river.
        #     They have a boat that can only carry three things at once. How do they do it?
        #     Conclude with your opinion as a one-sentence answer.
        # """,
        # ),
    ]


class JudgmentTestCases:
    """Live judgment material, and every string in it is pinned on purpose.

    The spike measured what moves an answer: repeating the same request moved a borderline case by
    0.01, while rewording a single instruction moved it from 0.11 to 0.30. So the wording here is
    part of the test, copied from the spike's recorded three-question probe, and a failure after an
    innocent-looking edit to it is telling the truth. Verdicts are asserted exactly; a probability
    gets ``PROBABILITY_MARGIN``, fifteen times the noise the spike observed.
    """

    PROBABILITY_MARGIN = 0.05

    STATE: ClassVar[dict[str, Any]] = {
        "message": (
            "Our production checkout has been returning 500s for every card payment since 09:14 UTC. "
            "Nothing is going through. I have three customers on the phone right now. Please help."
        ),
        "channel": "support_email",
    }

    IS_URGENT = YesNoQuestion(
        instructions="Is the message urgent?",
        yes_criterion="Needs attention now",
        no_criterion="Can wait until the next working day",
    )
    TEAM = ChoiceQuestion(
        instructions="Which team should handle this message?",
        options={
            "payments": "Charges, invoices, payment processing failures",
            "shipping": "Delivery status, delays, lost packages",
            "accounts": "Sign-in, passwords, account settings",
            "other": "None of the above",
        },
    )
    SEVERITY = RatingQuestion(
        instructions="How severe is the reported issue?",
        levels=[
            "Cosmetic; no impact on functionality",
            "A feature is degraded, but a workaround exists",
            "Blocking issue; no workaround exists",
        ],
    )

    THREE_QUESTIONS: ClassVar[dict[str, JudgmentQuestion]] = {
        "is_urgent": IS_URGENT,
        "team": TEAM,
        "severity": SEVERITY,
    }

    # (topic, question, kind) — each kind alone, as a batch of one, on the unambiguous case.
    EACH_KIND: ClassVar[list[tuple[str, JudgmentQuestion, JudgmentKind]]] = [
        ("yes_no", IS_URGENT, JudgmentKind.YES_NO),
        ("choice", TEAM, JudgmentKind.CHOICE),
        ("rating", SEVERITY, JudgmentKind.RATING),
    ]

    # What the spike recorded for this material, bit-identical across eight repeats.
    EXPECTED_IS_URGENT_PROBABILITY = 0.98
    EXPECTED_TEAM = "payments"
    EXPECTED_SEVERITY_LEVEL = 2


class JudgmentTestCharge(StructuredContent):
    amount_usd: float
    status: str


class JudgmentTestOrder(StructuredContent):
    order_id: str
    charges: list[JudgmentTestCharge]
    tracking_number: str | None = None


@dataclass(frozen=True)
class JudgmentStateShapeCase:
    """One question over two states that differ only in the value under test, and the exact state each side must produce."""

    question: YesNoQuestion
    yes_inputs: dict[str, StuffContent]
    no_inputs: dict[str, StuffContent]
    expected_yes_state: JudgmentState
    expected_no_state: JudgmentState


def _judgment_order(*, charges: list[JudgmentTestCharge], tracking_number: str | None = None) -> JudgmentTestOrder:
    return JudgmentTestOrder(order_id="A-104", charges=charges, tracking_number=tracking_number)


class JudgmentStateShapeCases:
    """Every JSON shape a PipeJudge puts in its judgment material, as yes/no pairs for the live judging model.

    Like `JudgmentTestCases`, the wording is part of the test: a question that makes the model do
    arithmetic over the material measures its arithmetic, not whether it read the shape. Asking
    "Does the refund cover every duplicate charge?" over three charges landed at 0.66 where the
    simpler question below lands at 0.99.
    """

    # A verdict must clear the middle by this much on its side: a shape the model half-read would hover near 0.5.
    CLEAR_YES = 0.8
    CLEAR_NO = 0.2

    CAPTURED = JudgmentTestCharge(amount_usd=49, status="captured")
    CAPTURED_STATE: ClassVar[dict[str, Any]] = {"amount_usd": 49, "status": "captured"}

    SHAPE_CASES: ClassVar[list[tuple[str, JudgmentStateShapeCase]]] = [  # topic, case
        (
            "text_as_string",
            JudgmentStateShapeCase(
                question=YesNoQuestion(instructions="Does the customer ask for a refund?"),
                yes_inputs={"message": TextContent(text="I was charged twice for my order. Please refund the duplicate charge.")},
                no_inputs={"message": TextContent(text="Thanks, my parcel arrived this morning and everything is fine.")},
                expected_yes_state={"message": "I was charged twice for my order. Please refund the duplicate charge."},
                expected_no_state={"message": "Thanks, my parcel arrived this morning and everything is fine."},
            ),
        ),
        (
            "integer_as_number",
            JudgmentStateShapeCase(
                question=YesNoQuestion(instructions="Is the order total above 1000 USD?"),
                yes_inputs={"order_total_usd": NumberContent(number=1240)},
                no_inputs={"order_total_usd": NumberContent(number=40)},
                expected_yes_state={"order_total_usd": 1240},
                expected_no_state={"order_total_usd": 40},
            ),
        ),
        (
            "float_as_number",
            JudgmentStateShapeCase(
                question=YesNoQuestion(instructions="Is the account balance negative?"),
                yes_inputs={"balance_usd": NumberContent(number=-12.75)},
                no_inputs={"balance_usd": NumberContent(number=312.5)},
                expected_yes_state={"balance_usd": -12.75},
                expected_no_state={"balance_usd": 312.5},
            ),
        ),
        (
            "yes_no_as_boolean",
            JudgmentStateShapeCase(
                question=YesNoQuestion(instructions="Has the refund been approved?"),
                yes_inputs={"refund_approved": YesNoContent(yes_no=True)},
                no_inputs={"refund_approved": YesNoContent(yes_no=False)},
                expected_yes_state={"refund_approved": True},
                expected_no_state={"refund_approved": False},
            ),
        ),
        (
            "dates_as_iso_strings",
            JudgmentStateShapeCase(
                question=YesNoQuestion(instructions="Was the parcel delivered more than a week after the order was placed?"),
                yes_inputs={
                    "ordered_on": DateContent(date=datetime.date(2026, 9, 1)),
                    "delivered_on": DateContent(date=datetime.date(2026, 9, 20)),
                },
                no_inputs={
                    "ordered_on": DateContent(date=datetime.date(2026, 9, 1)),
                    "delivered_on": DateContent(date=datetime.date(2026, 9, 3)),
                },
                expected_yes_state={"ordered_on": "2026-09-01", "delivered_on": "2026-09-20"},
                expected_no_state={"ordered_on": "2026-09-01", "delivered_on": "2026-09-03"},
            ),
        ),
        (
            "time_as_iso_string",
            JudgmentStateShapeCase(
                question=YesNoQuestion(instructions="Did the call take place in the middle of the night?"),
                yes_inputs={"call_time": TimeContent(time=datetime.time(3, 15))},
                no_inputs={"call_time": TimeContent(time=datetime.time(14, 30))},
                expected_yes_state={"call_time": "03:15:00"},
                expected_no_state={"call_time": "14:30:00"},
            ),
        ),
        (
            "json_as_nested_object",
            JudgmentStateShapeCase(
                question=YesNoQuestion(instructions="Did the fraud check flag this payment?"),
                yes_inputs={"payment_checks": JSONContent(json_obj={"fraud": {"flagged": True, "score": 0.97}, "3ds": "passed"})},
                no_inputs={"payment_checks": JSONContent(json_obj={"fraud": {"flagged": False, "score": 0.02}, "3ds": "passed"})},
                expected_yes_state={"payment_checks": {"fraud": {"flagged": True, "score": 0.97}, "3ds": "passed"}},
                expected_no_state={"payment_checks": {"fraud": {"flagged": False, "score": 0.02}, "3ds": "passed"}},
            ),
        ),
        (
            "structure_as_nested_object_with_array",
            JudgmentStateShapeCase(
                question=YesNoQuestion(instructions="Was the customer charged more than once for this order?"),
                yes_inputs={"order": _judgment_order(charges=[CAPTURED, CAPTURED])},
                no_inputs={"order": _judgment_order(charges=[CAPTURED])},
                expected_yes_state={"order": {"order_id": "A-104", "charges": [CAPTURED_STATE, CAPTURED_STATE]}},
                expected_no_state={"order": {"order_id": "A-104", "charges": [CAPTURED_STATE]}},
            ),
        ),
        (
            # The no side is the point: the unset member is left out of the object, never sent as a null.
            "absent_member_left_out",
            JudgmentStateShapeCase(
                question=YesNoQuestion(instructions="Has a tracking number been assigned to the order?"),
                yes_inputs={"order": _judgment_order(charges=[CAPTURED], tracking_number="1Z999AA10123456784")},
                no_inputs={"order": _judgment_order(charges=[CAPTURED])},
                expected_yes_state={"order": {"order_id": "A-104", "charges": [CAPTURED_STATE], "tracking_number": "1Z999AA10123456784"}},
                expected_no_state={"order": {"order_id": "A-104", "charges": [CAPTURED_STATE]}},
            ),
        ),
        (
            "list_of_texts_as_array",
            JudgmentStateShapeCase(
                question=YesNoQuestion(instructions="Did the customer threaten to cancel their subscription?"),
                yes_inputs={
                    "messages": ListContent(items=[TextContent(text="This is the third time this happens."), TextContent(text="Fix it or I cancel.")])
                },
                no_inputs={
                    "messages": ListContent(
                        items=[TextContent(text="This is the third time this happens."), TextContent(text="Thanks for the quick fix.")]
                    )
                },
                expected_yes_state={"messages": ["This is the third time this happens.", "Fix it or I cancel."]},
                expected_no_state={"messages": ["This is the third time this happens.", "Thanks for the quick fix."]},
            ),
        ),
        (
            "list_of_structures_as_array_of_objects",
            JudgmentStateShapeCase(
                question=YesNoQuestion(instructions="Was any of these charges refunded?"),
                yes_inputs={"charges": ListContent(items=[CAPTURED, JudgmentTestCharge(amount_usd=49, status="refunded")])},
                no_inputs={"charges": ListContent(items=[CAPTURED, CAPTURED])},
                expected_yes_state={"charges": [CAPTURED_STATE, {"amount_usd": 49, "status": "refunded"}]},
                expected_no_state={"charges": [CAPTURED_STATE, CAPTURED_STATE]},
            ),
        ),
        (
            "earlier_verdict_as_object",
            JudgmentStateShapeCase(
                question=YesNoQuestion(instructions="Was the message routed to the payments team?"),
                yes_inputs={"routing": ChoiceContent(choice="payments", confidence=0.93)},
                no_inputs={"routing": ChoiceContent(choice="shipping", confidence=0.93)},
                expected_yes_state={"routing": {"choice": "payments", "confidence": 0.93}},
                expected_no_state={"routing": {"choice": "shipping", "confidence": 0.93}},
            ),
        ),
        (
            "html_as_wrapped_object",
            JudgmentStateShapeCase(
                question=YesNoQuestion(instructions="Does the page ask the visitor for a password?"),
                yes_inputs={"page": HtmlContent(inner_html='<form><label>Password</label><input type="password" name="pw"></form>')},
                no_inputs={"page": HtmlContent(inner_html="<p>Our offices are closed on public holidays.</p>")},
                expected_yes_state={"page": {"inner_html": '<form><label>Password</label><input type="password" name="pw"></form>'}},
                expected_no_state={"page": {"inner_html": "<p>Our offices are closed on public holidays.</p>"}},
            ),
        ),
        (
            "several_inputs_related",
            JudgmentStateShapeCase(
                question=YesNoQuestion(instructions="Is the refund amount equal to the amount of one charge on the order?"),
                yes_inputs={"order": _judgment_order(charges=[CAPTURED, CAPTURED]), "refund_usd": NumberContent(number=49)},
                no_inputs={"order": _judgment_order(charges=[CAPTURED, CAPTURED]), "refund_usd": NumberContent(number=5)},
                expected_yes_state={"order": {"order_id": "A-104", "charges": [CAPTURED_STATE, CAPTURED_STATE]}, "refund_usd": 49},
                expected_no_state={"order": {"order_id": "A-104", "charges": [CAPTURED_STATE, CAPTURED_STATE]}, "refund_usd": 5},
            ),
        ),
    ]

    # The same fact in the typed shape a PipeJudge sends, and in the stringified or flattened shape it could have
    # sent instead. Each pair must land on the same side: the typed shape loses nothing to the alternative.
    EQUIVALENT_SHAPES: ClassVar[list[tuple[str, YesNoQuestion, JudgmentState, JudgmentState, bool]]] = [
        # topic, question, typed_state, alternative_state, expected_yes
        (
            "boolean_true_vs_word",
            YesNoQuestion(instructions="Has the refund been approved?"),
            {"refund_approved": True},
            {"refund_approved": "yes"},
            True,
        ),
        (
            "boolean_false_vs_word",
            YesNoQuestion(instructions="Has the refund been approved?"),
            {"refund_approved": False},
            {"refund_approved": "no"},
            False,
        ),
        (
            "number_vs_numeric_string",
            YesNoQuestion(instructions="Is the order total above 1000 USD?"),
            {"order_total_usd": 1240},
            {"order_total_usd": "1240"},
            True,
        ),
        (
            "nested_vs_flattened_strings",
            YesNoQuestion(instructions="Was the customer charged more than once for this order?"),
            {"order": {"order_id": "A-104", "charges": [CAPTURED_STATE, CAPTURED_STATE]}},
            {
                "order.order_id": "A-104",
                "order.charges.0.amount_usd": "49",
                "order.charges.0.status": "captured",
                "order.charges.1.amount_usd": "49",
                "order.charges.1.status": "captured",
            },
            True,
        ),
    ]
