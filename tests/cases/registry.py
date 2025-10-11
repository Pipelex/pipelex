"""Registry and model constants for testing."""

from typing import ClassVar

from pydantic import BaseModel
from typing_extensions import override


class ClassRegistryTestCases:
    """Class registry test constants."""

    MODEL_FOLDER_PATH = "tests/data/tools_data/mock_folder_with_classes"

    CLASSES_TO_REGISTER: ClassVar[list[str]] = [
        "Class1",
        "Class2",
        "Class3",
        "Class4",
    ]

    CLASSES_NOT_TO_REGISTER: ClassVar[list[str]] = [
        "ClassA",
        "ClassB",
    ]


class FileHelperTestCases:
    """File helper test constants."""

    TEST_IMAGE = "tests/data/tools_data/images/white_square.png"


class Fruit(BaseModel):
    """Test model for fruit data."""

    name: str
    color: str

    @override
    def __str__(self) -> str:
        return self.name
