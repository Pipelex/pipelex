"""Compare a class the structure generator builds with the class a test writes out by hand.

The generator builds its class from data, so a test states what it expects as the class a person would write: Python
source the test itself holds, executed here against the names a structure class can use. The two classes agree when
their bases, docstrings and fields agree, and, once every forward reference resolves, their JSON schemas.
"""

import inspect
from datetime import date, datetime, time
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.non_null_any import NonNullAny
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent

# The names the expected classes of the tests read.
_EXPECTED_CLASS_NAMES: dict[str, Any] = {
    "Any": Any,
    "Literal": Literal,
    "Optional": Optional,
    "Field": Field,
    "date": date,
    "datetime": datetime,
    "time": time,
    "NonNullAny": NonNullAny,
    "StructuredContent": StructuredContent,
    "TextContent": TextContent,
    "ImageContent": ImageContent,
    "NumberContent": NumberContent,
    "JSONContent": JSONContent,
    "DocumentContent": DocumentContent,
    "HtmlContent": HtmlContent,
}


def make_expected_class(*, expected_source: str, class_name: str) -> type[BaseModel]:
    """Execute the source of the one class a test expects and return that class."""
    namespace: dict[str, Any] = dict(_EXPECTED_CLASS_NAMES)
    exec(expected_source, namespace)
    expected_class = namespace[class_name]
    assert isinstance(expected_class, type)
    assert issubclass(expected_class, BaseModel)
    return expected_class


def _field_table(model_class: type[BaseModel]) -> dict[str, tuple[Any, bool, Any, str | None]]:
    return {
        field_name: (field_info.annotation, field_info.is_required(), field_info.default, field_info.description)
        for field_name, field_info in model_class.model_fields.items()
    }


def assert_same_class(generated_class: type[Any], *, expected_source: str) -> None:
    """Assert that the generated class is the class `expected_source` defines under the same name."""
    assert issubclass(generated_class, BaseModel)
    expected_class = make_expected_class(expected_source=expected_source, class_name=generated_class.__name__)
    assert generated_class.__bases__ == expected_class.__bases__
    assert inspect.getdoc(generated_class) == inspect.getdoc(expected_class)
    assert _field_table(generated_class) == _field_table(expected_class)
    if generated_class.__pydantic_complete__ and expected_class.__pydantic_complete__:
        assert generated_class.model_json_schema() == expected_class.model_json_schema()
