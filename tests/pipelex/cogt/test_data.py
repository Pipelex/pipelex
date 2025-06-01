from enum import StrEnum
from typing import ClassVar, List, Tuple

from pydantic import BaseModel, Field, field_validator

from tests.pipelex.test_data import PipeTestCases


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
    VISION_USER_TEXT_2 = "What is this image about ?"
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

    IMAGE_PATHS: ClassVar[List[Tuple[str, str]]] = [  # topic, image_path
        ("AI Lympics PNG", PATH_IMG_PNG_1),
        ("AI Lympics JPEG", PATH_IMG_JPEG_1),
        ("Gantt Chart", PATH_IMG_GANTT_1),
    ]
    IMAGE_PATH_PAIRS: ClassVar[List[Tuple[str, Tuple[str, str]]]] = [  # topic, image_pair
        ("AI Lympics PNG", (PATH_IMG_PNG_1, PATH_IMG_PNG_2)),
    ]

    IMAGES_MIXED_SOURCES: ClassVar[List[Tuple[str, str]]] = [  # topic, image_uri
        (
            "Alan Turing",
            URL_WIKIPEDIA_ALAN_TURING,
        ),
        (
            "AI Lympics",
            PATH_IMG_PNG_1,
        ),
        (
            "Eiffel Tower",
            PATH_IMG_JPEG_3,
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
    PROMPT_COLOR_EXAMPLES: ClassVar[List[str]] = [
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
    SINGLE_TEXT: ClassVar[List[Tuple[str, str]]] = [  # topic, prompt_text
        ("Haiku", USER_TEXT_HAIKU),
        ("Tricky", USER_TEXT_TRICKY),
    ]
    SINGLE_OBJECT: ClassVar[List[Tuple[str, BaseModel]]] = [
        ("name: John, age: 30", Person(name="John", age=30)),
        ("Betty Draper, 51", Person(name="Betty Draper", age=51)),
        ("Whiskers, the cat", Pet(species=PetSpecies.CAT, name="Whiskers")),
        ("Whiskers, the dog", Pet(species=PetSpecies.DOG, name="Whiskers")),
    ]
    MULTIPLE_OBJECTS: ClassVar[List[List[Tuple[str, BaseModel]]]] = [
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
