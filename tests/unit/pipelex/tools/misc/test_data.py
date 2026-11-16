from typing import ClassVar

from pydantic import BaseModel, Field


class Address(BaseModel):
    street: str
    city: str
    country: str
    postal_code: str | None = None


class UserPreferences(BaseModel):
    theme: str = "dark"
    notifications: bool = True
    tags: list[str] = Field(default_factory=list)


class ComplexUser(BaseModel):
    name: str
    age: int
    email: str | None
    addresses: list[Address]
    preferences: UserPreferences
    metadata: dict[str, str | int | bool] = Field(default_factory=dict)


class ImageData(BaseModel):
    """Model with base64 image data for testing truncation."""

    name: str
    base_64: str
    url: str | None = None


class PythonLiteralsTestData:
    """Strings for the tests of `pipelex.tools.misc.python_literals`."""

    # Characters `str.splitlines` treats as line breaks although `inspect.cleandoc` does not.
    SPLITLINES_ONLY_BREAKS: ClassVar[list[str]] = ["\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", " ", " "]

    # The alphabet the randomized round-trip draws from: quotes, backslashes, control characters, NUL, line
    # separators, spaces and tabs for indentation, and ordinary letters.
    RANDOM_ALPHABET: ClassVar[list[str]] = [
        *SPLITLINES_ONLY_BREAKS,
        "a",
        "b",
        " ",
        " ",
        "  ",
        "\t",
        "\n",
        "\n",
        "\r",
        "\r\n",
        '"',
        "'",
        '"""',
        "'''",
        "\\",
        "\x00",
        "\x07",
        "\x1b",
    ]
