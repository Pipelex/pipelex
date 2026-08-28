"""Narrowing accessors for the input-form descriptor's discriminated union.

The descriptor's field models come from `mthds.protocol.input_form`, where a node's kind IS its
model and `InputFormField` is their union discriminated on `kind`. A test that reads a per-kind
slot — `fields` on an object node, `item` on a list node, `integer` on a number node — must narrow
to that model first, and a failed narrowing is exactly the assertion the test meant to make. These
helpers do both in one gesture, so a test that expected one kind and got another fails saying which
kind arrived.
"""

from __future__ import annotations

from typing import TypeVar

from pipelex.pipeline.input_form import InputFormField, InputFormItemBase, ListField, ObjectField

FieldModelType = TypeVar("FieldModelType", bound=InputFormItemBase)


def as_kind(node: InputFormField, kind_model: type[FieldModelType]) -> FieldModelType:
    """The node, narrowed to one per-kind model — asserting the kind on the way through."""
    assert isinstance(node, kind_model), f"Expected a '{kind_model.__name__}' node, got '{node.kind}'"
    return node


def as_object(node: InputFormField) -> ObjectField:
    """The node, narrowed to an `object`."""
    return as_kind(node, ObjectField)


def as_list(node: InputFormField) -> ListField:
    """The node, narrowed to a `list`."""
    return as_kind(node, ListField)


def fields_by_name(node: InputFormField) -> dict[str, InputFormField]:
    """An object node's payload fields keyed by their authored name."""
    return {field.name: field for field in as_object(node).fields}
