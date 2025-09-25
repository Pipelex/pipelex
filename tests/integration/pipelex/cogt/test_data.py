from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator

from pipelex.cogt.image.prompt_image import PromptImagePath
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_template import LLMPromptTemplate
from pipelex.cogt.llm.llm_prompt_template_inputs import LLMPromptTemplateInputs
from pipelex.types import StrEnum
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
            raise ValueError("job title must be lowercase")
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


class LLMVisionTestCases:
    VISION_USER_TEXT_1 = "Describe the provide image."
    VISION_USER_TEXT_2 = "What is this image about?"
    VISION_IMAGES_COMPARE_PROMPT = "Compare these two images"

    URL_WIKIPEDIA_ALAN_TURING = "https://upload.wikimedia.org/wikipedia/commons/thumb/4/40/Alan_Turing_%281912-1954%29_in_1936_at_Princeton_University_%28cropped%29.jpg/440px-Alan_Turing_%281912-1954%29_in_1936_at_Princeton_University_%28cropped%29.jpg"

    TEST_IMAGE_DIRECTORY = "tests/data/images"

    PATH_IMG_PNG_1 = f"{TEST_IMAGE_DIRECTORY}/ai_lympics.png"
    PATH_IMG_JPEG_1 = f"{TEST_IMAGE_DIRECTORY}/ai_lympics.jpg"

    PATH_IMG_PNG_2 = f"{TEST_IMAGE_DIRECTORY}/animal_lympics.png"
    PATH_IMG_JPEG_2 = f"{TEST_IMAGE_DIRECTORY}/animal_lympics.jpg"

    PATH_IMG_PNG_3 = f"{TEST_IMAGE_DIRECTORY}/eiffel_tower.png"
    PATH_IMG_JPEG_3 = f"{TEST_IMAGE_DIRECTORY}/eiffel_tower.jpg"

    PATH_IMG_GANTT_1 = f"{TEST_IMAGE_DIRECTORY}/gantt_tree_house.png"

    IMAGE_PATHS: ClassVar[list[tuple[str, str]]] = [  # topic, image_path
        ("AI Lympics PNG", PATH_IMG_PNG_1),
        ("AI Lympics JPEG", PATH_IMG_JPEG_1),
        ("Gantt Chart", PATH_IMG_GANTT_1),
        ("Eiffel Tower", PATH_IMG_JPEG_3),
    ]
    IMAGE_PATH_PAIRS: ClassVar[list[tuple[str, tuple[str, str]]]] = [  # topic, image_pair
        ("AI Lympics PNG", (PATH_IMG_PNG_1, PATH_IMG_PNG_2)),
    ]

    IMAGE_URLS: ClassVar[list[tuple[str, str]]] = [  # topic, image_uri
        (
            "Alan Turing",
            URL_WIKIPEDIA_ALAN_TURING,
        ),
        (
            "Gantt chart",
            PipeTestCases.URL_IMG_GANTT_1,
        ),
    ]


class LLMTestConstants:
    USER_TEXT_SHORT = "In one sentence, who is Bill Gates?"
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
            ("Whiskers, the cat", Pet(species=PetSpecies.CAT, name="Whiskers")),
            ("Whiskers, the dog", Pet(species=PetSpecies.DOG, name="Whiskers")),
        ],
        [
            # ("name: Alice, age: 25", Person(name="Alice", age=25)),
            ("My sister's plumber, Bob Smith, is 42", Employee(name="Bob Smith", age=42, job="plumber")),
            ("Fluffy, the hamster", Pet(species=PetSpecies.HAMSTER, name="Fluffy")),
            ("Rex, the dog", Pet(species=PetSpecies.DOG, name="Rex")),
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

    # Prompt containing an image path --------------------------------------
    PROMPT_WITH_IMAGE_PATH: ClassVar[LLMPrompt] = LLMPrompt(
        system_text="Some system text",
        user_text="Some user text",
        user_images=[
            PromptImagePath(file_path="some_file_path"),
        ],
    )

    # Group constants for parametrization ----------------------------------
    PYDANTIC_EXAMPLES: ClassVar[list[BaseModel]] = [
        MY_PROMPT_TEMPLATE_MODEL_1,
        MY_PROMPT_TEMPLATE_MODEL_2,
    ]
    PYDANTIC_EXAMPLES_USING_SUBCLASS: ClassVar[list[BaseModel]] = [
        PROMPT_WITH_IMAGE_PATH,
    ]
    PYDANTIC_EXAMPLES_DICT: ClassVar[list[dict[str, Any]]] = [
        DICT_1,
    ]
