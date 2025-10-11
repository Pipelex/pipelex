from typing import Literal

from pydantic import Field

from pipelex.core.stuffs.stuff_content import StructuredContent
from pipelex.types import StrEnum


class MusicGenre(StrEnum):
    """Available music genres."""

    CLASSICAL = "classical"
    JAZZ = "jazz"
    ROCK = "rock"
    ELECTRONIC = "electronic"
    WORLD = "world"


class MusicCategoryContent(StructuredContent):
    """A content class with a Literal field for music genres."""

    category: Literal[
        MusicGenre.CLASSICAL,
        MusicGenre.JAZZ,
        MusicGenre.ROCK,
        MusicGenre.ELECTRONIC,
        MusicGenre.WORLD,
    ] = Field(description="The genre of music")


class SimpleTextContent(StructuredContent):
    """A simple text content class for testing."""

    text: str = Field(description="The text content")


class SimpleStructuredContent(StructuredContent):
    """A structured content class with primitive types."""

    name: str = Field(description="The name of the content")
    value: int = Field(description="The numeric value")
    is_active: bool = Field(description="Whether the content is active")


class DocumentTypeContent(StructuredContent):
    """A content class with enum fields."""

    title: str = Field(description="The document title")
    status: str = Field(description="The document status")


class PersonContent(StructuredContent):
    """A complex nested content with various types."""

    name: str = Field(description="The person's name")
    age: int = Field(description="The person's age")
    address: str = Field(description="The person's address")


class ComplexListContent(StructuredContent):
    """A content class with list fields."""

    items: list[str] = Field(description="List of items")
    tags: list[str] = Field(description="List of tags")
