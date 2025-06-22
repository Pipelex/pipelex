from typing import ClassVar, List

from pydantic import BaseModel
from typing_extensions import override

from pipelex.tools.templating.templating_models import PromptingStyle, TagStyle, TextFormat


class TestURLs:
    URL_GCP_PUBLIC = "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/diagrams/gantt_tree_house.png"
    URL_WIKIPEDIA = "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ec/Olympic_rings_on_the_Eiffel_Tower_2024_%2819%29.jpg/440px-Olympic_rings_on_the_Eiffel_Tower_2024_%2819%29.jpg"

    PUBLIC_URLS: ClassVar[List[str]] = [
        URL_GCP_PUBLIC,
        URL_WIKIPEDIA,
    ]


class ClassRegistryTestCases:
    MODEL_FOLDER_PATH = "tests/data/tools_data/mock_folder_with_classes"
    CLASSES_TO_REGISTER: ClassVar[List[str]] = [
        "Class1",
        "Class2",
        "Class3",
        "Class4",
    ]
    CLASSES_NOT_TO_REGISTER: ClassVar[List[str]] = [
        "ClassA",
        "ClassB",
    ]


class FileHelperTestCases:
    TEST_IMAGE = "tests/data/tools_data/images/white_square.png"


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
