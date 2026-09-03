"""How a Python type annotation maps onto the MTHDS shape vocabulary.

Two reflections in this engine read registered pydantic classes and ask an annotation the same
questions: the native consistency probe (`pipelex/codegen/native_expansion.py`), which reflects a
native's content class into blueprint form, and the input-form deriver
(`pipelex/pipeline/input_form.py`), which reflects a class-backed concept into descriptor nodes.
What they build differs, and so does what they do with an annotation neither can map — the probe
answers absent, the deriver emits an `unknown` node — but the questions themselves live here, so
the two reflections cannot come to different answers about the same annotation.
"""

import datetime
from types import UnionType
from typing import Any, Union, get_args, get_origin

from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprintFieldType
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.stuff_content import StuffContent

_NATIVE_CLASS_NAME_TO_CODE: dict[str, NativeConceptCode] = {native_code.structure_class_name: native_code for native_code in NativeConceptCode}


def strip_optional(*, annotation: Any) -> tuple[Any, bool]:
    """Return (inner, required): peel a single `X | None` into (X, False); otherwise (annotation, True)."""
    if get_origin(annotation) in {Union, UnionType}:
        args = get_args(annotation)
        non_none = [arg for arg in args if arg is not type(None)]
        if len(non_none) == 1 and len(non_none) != len(args):
            return non_none[0], False
    return annotation, True


def is_union(*, annotation: Any) -> bool:
    """Whether the annotation is a union — asked after `strip_optional`, so `X | None` is already gone."""
    return get_origin(annotation) in {Union, UnionType}


def is_number_union(*, annotation: Any) -> bool:
    """Whether the annotation is exactly `int | float`, the one union with a single MTHDS shape."""
    if not is_union(annotation=annotation):
        return False
    return set(get_args(annotation)) == {int, float}


def scalar_field_type(*, annotation: Any) -> ConceptStructureBlueprintFieldType | None:
    """The scalar MTHDS field type of the annotation, or `None` when it is not a scalar."""
    # Order matters: bool is an int subclass, datetime is a date subclass — check the narrower first.
    if annotation is bool:
        return ConceptStructureBlueprintFieldType.BOOLEAN
    if annotation is int:
        return ConceptStructureBlueprintFieldType.INTEGER
    if annotation is float:
        return ConceptStructureBlueprintFieldType.NUMBER
    if annotation is str:
        return ConceptStructureBlueprintFieldType.TEXT
    if annotation is datetime.datetime:
        return ConceptStructureBlueprintFieldType.DATETIME
    if annotation is datetime.date:
        return ConceptStructureBlueprintFieldType.DATE
    if annotation is datetime.time:
        return ConceptStructureBlueprintFieldType.TIME
    return None


def native_code_for_content_class(*, annotation: Any) -> NativeConceptCode | None:
    """The native concept a content class stands for, decided by identity — never by shape."""
    if not isinstance(annotation, type) or not issubclass(annotation, StuffContent):
        return None
    return _NATIVE_CLASS_NAME_TO_CODE.get(annotation.__name__)


def list_item_annotation(*, annotation: Any) -> Any:
    """The element annotation of a list, already peeled of an `X | None` wrapper; `None` when unparameterized."""
    args = get_args(annotation)
    if not args:
        return None
    inner, _ = strip_optional(annotation=args[0])
    return inner
