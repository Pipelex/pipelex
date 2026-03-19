from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator

from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_template import LLMPromptTemplate
from pipelex.cogt.llm.llm_prompt_template_inputs import LLMPromptTemplateInputs
from pipelex.types import StrEnum
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
    """Constants and example objects used for SerDe unit tests."""

    # Base building blocks -------------------------------------------------
    PROTO_PROMPT: ClassVar[LLMPrompt] = LLMPrompt(
        user_text="Some user text in the template",
    )

    BASE_TEMPLATE_INPUTS_1: ClassVar[LLMPromptTemplateInputs] = LLMPromptTemplateInputs(
        root={"foo": "bar"},
    )
    MY_PROMPT_TEMPLATE_MODEL_1: ClassVar[LLMPromptTemplate] = LLMPromptTemplate(
        proto_prompt=PROTO_PROMPT,
        base_template_inputs=BASE_TEMPLATE_INPUTS_1,
    )

    BASE_TEMPLATE_INPUTS_2: ClassVar[LLMPromptTemplateInputs] = LLMPromptTemplateInputs(
        root={},
    )
    MY_PROMPT_TEMPLATE_MODEL_2: ClassVar[LLMPromptTemplate] = LLMPromptTemplate(
        proto_prompt=PROTO_PROMPT,
        base_template_inputs=BASE_TEMPLATE_INPUTS_2,
    )

    # Dictionary representation example ------------------------------------
    DICT_1: ClassVar[dict[str, Any]] = {
        "proto_prompt": LLMPrompt(
            system_text=None,
            user_text="Some user text in the template",
            user_images=[],
        ),
        "base_template_inputs": LLMPromptTemplateInputs(root={}),
        "source_system_template_name": None,
        "source_user_template_name": "markdown_reordering_vision_claude3_5_sonnet",
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
        MY_PROMPT_TEMPLATE_MODEL_1,
        MY_PROMPT_TEMPLATE_MODEL_2,
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
