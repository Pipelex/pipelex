import ast
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from pipelex import pretty_print
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.misc.python_literals import normalized_docstring_text
from pipelex.tools.typing.structure_printer import StructurePrinter


# Test Enums
class DocumentType(StrEnum):
    INVOICE = "INVOICE"
    RECEIPT = "RECEIPT"


class Priority(StrEnum):
    HIGH = "HIGH"
    LOW = "LOW"


class MusicGenre(StrEnum):
    """Available music genres."""

    CLASSICAL = "classical"
    JAZZ = "jazz"
    ROCK = "rock"
    ELECTRONIC = "electronic"
    WORLD = "world"


# Simple Content Classes
class SimpleTextContent(TextContent):
    """A simple text content class"""


class MusicCategoryContent(StructuredContent):
    """A content class with a Literal field for music genres."""

    category: Literal[
        MusicGenre.CLASSICAL,
        MusicGenre.JAZZ,
        MusicGenre.ROCK,
        MusicGenre.ELECTRONIC,
        MusicGenre.WORLD,
    ] = Field(description="The genre of music")


class SimpleStructuredContent(StructuredContent):
    """A simple structured content with primitive types"""

    name: str
    age: int
    active: bool


# Enum Content Classes
class DocumentTypeContent(StructuredContent):
    """Content with enum type"""

    document_type: DocumentType


# Nested Content Classes
class AddressContent(StructuredContent):
    """Nested address content"""

    street: str
    city: str
    country: str


class PersonContent(StructuredContent):
    """Complex nested content with various types"""

    name: str
    age: int
    address: AddressContent = Field(description="Address of the person")
    documents: list[DocumentTypeContent]
    priority: Priority | None = None


class ComplexListContent(ListContent[PersonContent]):
    """List content with complex items"""

    items: list[PersonContent]


class GanttTaskDetails(StructuredContent):
    """Do not include timezone in the dates."""

    name: str
    start_date: datetime | None = None
    end_date: datetime | None = None

    @field_validator("start_date", "end_date")
    @classmethod
    def remove_tzinfo(cls, v: datetime | None) -> datetime | None:
        if v is not None:
            return v.replace(tzinfo=None)
        return v


class Milestone(StructuredContent):
    name: str
    date: datetime | None

    @field_validator("date")
    @classmethod
    def remove_tzinfo(cls, v: datetime | None) -> datetime | None:
        if v is not None:
            return v.replace(tzinfo=None)
        return v


class GanttChart(StructuredContent):
    tasks: list[GanttTaskDetails] | None = None
    milestones: list[Milestone] | None = None


class QuotedGenre(StrEnum):
    JAZZ = "jazz"


# Assigned after the class is built so that the test source itself holds no docstring of this shape.
QuotedGenre.__doc__ = 'A genre list naming """ quotes and ending in a backslash \\'


class QuotedContent(StructuredContent):
    genre: QuotedGenre = Field(description="The genre")


QuotedContent.__doc__ = 'Says """hello""" in a list:\n  - with an indented line\nand ends with a backslash \\'


class OddValue(StrEnum):
    QUOTED = 'says "hi" and \\ a backslash'
    APOSTROPHE = "it's"


class OddValueContent(StructuredContent):
    odd: OddValue
    choice: Literal['says "hi"', "it's"]


class MultiLineDescriptionContent(StructuredContent):
    value: str = Field(description="first line\nb = 1\r\nc = 2\rd = 3")


class TestStructurePrinter:
    def test_simple_text_content(self):
        """Test structure of simple text content"""
        result = StructurePrinter().get_type_structure(SimpleTextContent)
        expected = [
            "class SimpleTextContent(TextContent):",
            '    """A simple text content class"""',
            "    # No additional fields",
        ]
        assert result == expected, f"Expected:\n{''.join(expected)}\n\nGot:\n{''.join(result)}"

    def test_simple_structured_content(self):
        """Test structure of simple structured content"""
        result = StructurePrinter().get_type_structure(SimpleStructuredContent)
        expected = [
            "class SimpleStructuredContent(StructuredContent):",
            '    """A simple structured content with primitive types"""',
            "    name: str",
            "    age: int",
            "    active: bool",
        ]
        assert result == expected, f"Expected:\n{''.join(expected)}\n\nGot:\n{''.join(result)}"

    def test_enum_content(self):
        """Test structure of content with enum"""
        result = StructurePrinter().get_type_structure(DocumentTypeContent)
        expected = [
            "class DocumentTypeContent(StructuredContent):",
            '    """Content with enum type"""',
            "    document_type: DocumentType",
            "",
            "class DocumentType(StrEnum):",
            '    INVOICE = "INVOICE"',
            '    RECEIPT = "RECEIPT"',
        ]
        assert result == expected, f"Expected:\n{''.join(expected)}\n\nGot:\n{''.join(result)}"

    def test_nested_content(self):
        """Test structure of nested content"""
        result = StructurePrinter().get_type_structure(PersonContent)
        expected = [
            "class PersonContent(StructuredContent):",
            '    """Complex nested content with various types"""',
            "    name: str",
            "    age: int",
            "    address: AddressContent  # Address of the person",
            "    documents: List[DocumentTypeContent]",
            "    priority: Priority | None = None",
            "",
            "class AddressContent(StructuredContent):",
            '    """Nested address content"""',
            "    street: str",
            "    city: str",
            "    country: str",
            "",
            "class DocumentTypeContent(StructuredContent):",
            '    """Content with enum type"""',
            "    document_type: DocumentType",
            "",
            "class DocumentType(StrEnum):",
            '    INVOICE = "INVOICE"',
            '    RECEIPT = "RECEIPT"',
            "",
            "class Priority(StrEnum):",
            '    HIGH = "HIGH"',
            '    LOW = "LOW"',
        ]

        pretty_print(result, title="results")
        pretty_print(expected, title="expected")
        assert result == expected, f"Expected:\n{''.join(expected)}\n\nGot:\n{''.join(result)}"

    def test_list_content(self):
        """Test structure of list content"""
        result = StructurePrinter().get_type_structure(ComplexListContent)
        expected = [
            "class ComplexListContent(ListContent[PersonContent]):",
            '    """List content with complex items"""',
            "    items: List[PersonContent]",
            "",
            "class PersonContent(StructuredContent):",
            '    """Complex nested content with various types"""',
            "    name: str",
            "    age: int",
            "    address: AddressContent  # Address of the person",
            "    documents: List[DocumentTypeContent]",
            "    priority: Priority | None = None",
            "",
            "class AddressContent(StructuredContent):",
            '    """Nested address content"""',
            "    street: str",
            "    city: str",
            "    country: str",
            "",
            "class DocumentTypeContent(StructuredContent):",
            '    """Content with enum type"""',
            "    document_type: DocumentType",
            "",
            "class DocumentType(StrEnum):",
            '    INVOICE = "INVOICE"',
            '    RECEIPT = "RECEIPT"',
            "",
            "class Priority(StrEnum):",
            '    HIGH = "HIGH"',
            '    LOW = "LOW"',
        ]
        assert result == expected, f"Expected:\n{''.join(expected)}\n\nGot:\n{''.join(result)}"

    def test_model_with_field_description(self):
        """Test structure of a model with field descriptions"""

        class Person(BaseModel):
            name: str
            age: int

        class Employee(Person):
            job: str = Field(description="Job title, must be lowercase")

        result = StructurePrinter().get_type_structure(Employee)
        expected = [
            "class Employee(Person):",
            "    job: str  # Job title, must be lowercase",
            "",
            "class Person(BaseModel):",
            "    name: str",
            "    age: int",
        ]
        assert result == expected, f"Expected:\n{''.join(expected)}\n\nGot:\n{''.join(result)}"

    def test_model_with_docstring_and_field_description(self):
        """Test structure of a model with both docstring and field descriptions"""

        class TaskContent(StructuredContent):
            """A task content model that represents a single task.

            This model is used to store task information including its title,
            description, and status.
            """

            title: str = Field(description="The title of the task")
            description: str = Field(description="Detailed description of what needs to be done")
            is_completed: bool = Field(default=False, description="Whether the task is completed")

        result = StructurePrinter().get_type_structure(TaskContent)
        expected = [
            "class TaskContent(StructuredContent):",
            '    """A task content model that represents a single task.',
            "",
            "    This model is used to store task information including its title,",
            "    description, and status.",
            '    """',
            "    title: str  # The title of the task",
            "    description: str  # Detailed description of what needs to be done",
            "    is_completed: bool = False  # Whether the task is completed",
        ]
        assert result == expected, f"Expected:\n{''.join(expected)}\n\nGot:\n{''.join(result)}"

    def test_literal_field_content(self) -> None:
        """Test structure of content with Literal field"""
        result = StructurePrinter().get_type_structure(MusicCategoryContent)
        expected = [
            "class MusicCategoryContent(StructuredContent):",
            '    """A content class with a Literal field for music genres."""',
            "    category: Literal[",
            '        "classical",',
            '        "jazz",',
            '        "rock",',
            '        "electronic",',
            '        "world",',
            "    ]  # The genre of music",
            "",
            "class MusicGenre(StrEnum):",
            '    """Available music genres."""',
            '    CLASSICAL = "classical"',
            '    JAZZ = "jazz"',
            '    ROCK = "rock"',
            '    ELECTRONIC = "electronic"',
            '    WORLD = "world"',
        ]
        assert result == expected, f"Expected:\n{''.join(expected)}\n\nGot:\n{''.join(result)}"

    def test_gantt_chart_content(self):
        result = StructurePrinter().get_type_structure(GanttChart, base_class=StructuredContent)
        expected = [
            "class GanttChart(StructuredContent):",
            "    tasks: List[GanttTaskDetails] | None = None",
            "    milestones: List[Milestone] | None = None",
            "",
            "class GanttTaskDetails(StructuredContent):",
            '    """Do not include timezone in the dates."""',
            "    name: str",
            "    start_date: datetime | None = None",
            "    end_date: datetime | None = None",
            "",
            "class Milestone(StructuredContent):",
            "    name: str",
            "    date: datetime | None = None",
        ]
        assert result == expected

    def test_docstrings_with_triple_quotes_render_verbatim(self):
        """A class or enum docstring containing triple quotes or a trailing backslash prints as a docstring that reads back as authored."""
        result = StructurePrinter().get_type_structure(QuotedContent)

        module = ast.parse("\n".join(result))
        class_defs = {node.name: node for node in module.body if isinstance(node, ast.ClassDef)}
        assert set(class_defs) == {"QuotedContent", "QuotedGenre"}
        assert ast.get_docstring(class_defs["QuotedContent"]) == normalized_docstring_text(QuotedContent.__doc__ or "")
        assert ast.get_docstring(class_defs["QuotedGenre"]) == normalized_docstring_text(QuotedGenre.__doc__ or "")

    def test_enum_and_literal_values_print_as_literals_of_themselves(self):
        """An enum member or a Literal value holding quotes or a backslash prints as a string literal that evaluates back to it."""
        result = StructurePrinter().get_type_structure(OddValueContent)

        module = ast.parse("\n".join(result))
        class_defs = {node.name: node for node in module.body if isinstance(node, ast.ClassDef)}
        assert set(class_defs) == {"OddValueContent", "OddValue"}
        member_values: dict[str, object] = {
            statement.targets[0].id: ast.literal_eval(statement.value)
            for statement in class_defs["OddValue"].body
            if isinstance(statement, ast.Assign) and isinstance(statement.targets[0], ast.Name)
        }
        assert member_values == {member.name: member.value for member in OddValue}
        choice = next(
            statement
            for statement in class_defs["OddValueContent"].body
            if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name) and statement.target.id == "choice"
        )
        assert isinstance(choice.annotation, ast.Subscript)
        assert ast.literal_eval(choice.annotation.slice) == ('says "hi"', "it's")

    def test_multi_line_field_description_continues_as_comments(self):
        """Every line of a multi-line field description prints as a comment, whatever line break ends the one before."""
        result = StructurePrinter().get_type_structure(MultiLineDescriptionContent)

        assert result == [
            "class MultiLineDescriptionContent(StructuredContent):",
            "    value: str  # first line",
            "    # b = 1",
            "    # c = 2",
            "    # d = 3",
        ]
        module = ast.parse("\n".join(result))
        class_def = module.body[0]
        assert isinstance(class_def, ast.ClassDef)
        assert [type(statement) for statement in class_def.body] == [ast.AnnAssign]
