from enum import StrEnum
from typing import List, Optional

from pytest import FixtureRequest

from pipelex.core.stuff_content import ListContent, StructuredContent, TextContent
from pipelex.tools.typing.type_inspector import get_type_structure


# Test Enums
class DocumentType(StrEnum):
    INVOICE = "INVOICE"
    RECEIPT = "RECEIPT"


class Priority(StrEnum):
    HIGH = "HIGH"
    LOW = "LOW"


# Simple Content Classes
class SimpleTextContent(TextContent):
    """A simple text content class"""

    pass


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
    address: AddressContent
    documents: List[DocumentTypeContent]
    priority: Optional[Priority] = None


class ComplexListContent(ListContent[PersonContent]):
    """List content with complex items"""

    items: List[PersonContent]


class TestTypeInspector:
    """Tests for the type inspector functionality"""

    def test_simple_text_content(self, request: FixtureRequest):
        """Test structure of simple text content"""
        result = get_type_structure(SimpleTextContent)
        expected = [
            "class SimpleTextContent(TextContent):",
            '    """A simple text content class"""',
            "    # Inherits from TextContent",
            "    # No additional fields",
        ]
        assert result == expected, f"Expected:\n{''.join(expected)}\n\nGot:\n{''.join(result)}"

    def test_simple_structured_content(self, request: FixtureRequest):
        """Test structure of simple structured content"""
        result = get_type_structure(SimpleStructuredContent)
        expected = [
            "class SimpleStructuredContent(StructuredContent):",
            '    """A simple structured content with primitive types"""',
            "    name: str",
            "    age: int",
            "    active: bool",
        ]
        assert result == expected, f"Expected:\n{''.join(expected)}\n\nGot:\n{''.join(result)}"

    def test_enum_content(self, request: FixtureRequest):
        """Test structure of content with enum"""
        result = get_type_structure(DocumentTypeContent)
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

    def test_nested_content(self, request: FixtureRequest):
        """Test structure of nested content"""
        result = get_type_structure(PersonContent)
        expected = [
            "class PersonContent(StructuredContent):",
            '    """Complex nested content with various types"""',
            "    name: str",
            "    age: int",
            "    address: AddressContent",
            "    documents: List[DocumentTypeContent]",
            "    priority: Optional[Priority] = None",
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

    def test_list_content(self, request: FixtureRequest):
        """Test structure of list content"""
        result = get_type_structure(ComplexListContent)
        expected = [
            "class ComplexListContent(ListContent[PersonContent]):",
            '    """List content with complex items"""',
            "    items: List[PersonContent]",
            "",
            "class PersonContent(StructuredContent):",
            '    """Complex nested content with various types"""',
            "    name: str",
            "    age: int",
            "    address: AddressContent",
            "    documents: List[DocumentTypeContent]",
            "    priority: Optional[Priority] = None",
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
