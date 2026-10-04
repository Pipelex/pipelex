"""The load-time check that every field a `PipeDocGen` template reads exists on its input's concept.

The blueprint checks that each variable a template reads is a declared input; this goes further, down each
path: `invoice.nosuch` is refused when the method loads, and so is `item.nosuch` in a loop over
`invoice.line_items`, which is followed back to the list's item concept. A path is checked only as far as the
concept's classes say what it holds: once it reaches a text, a number, a JSON value or a property or method of a
class, the check stops, and anything the static check cannot follow is caught by the strict undefined when the
template renders at the dry run.
"""

import types
import typing
from collections.abc import Sequence
from typing import Any, Union

from pydantic import BaseModel

from pipelex.cogt.templating.template_preprocessor import rewrite_template_sigils
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_artefact import StuffArtefact
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.pipe_operators.doc_gen.exceptions import PipeDocGenFactoryError
from pipelex.runtime_hub import get_class_registry
from pipelex.tools.jinja2.jinja2_field_paths import TemplateFieldPath, detect_template_field_paths
from pipelex.tools.jinja2.jinja2_scopes import LIST_ITEM_SEGMENT
from pipelex.tools.jinja2.template_category import TemplateCategory

_NONE_TYPE = type(None)


def _unwrap(annotation: Any) -> Any:
    """An optional or annotated type's own type; any other union is returned as is, and stops the check."""
    origin = typing.get_origin(annotation)
    if origin is typing.Annotated:
        return _unwrap(typing.get_args(annotation)[0])
    if origin in {Union, types.UnionType}:
        members = [member for member in typing.get_args(annotation) if member is not _NONE_TYPE]
        if len(members) == 1:
            return _unwrap(members[0])
    return annotation


def _list_item_type(annotation: Any) -> Any | None:
    if typing.get_origin(annotation) in {list, tuple, set, frozenset, Sequence}:
        item_args = typing.get_args(annotation)
        return item_args[0] if item_args else None
    return None


def _first_missing_field(*, start: Any, segments: tuple[str, ...]) -> tuple[int, type[BaseModel]] | None:
    """The index of the first segment naming no field of the class it is read on, with that class; None when the path holds.

    A segment the classes cannot answer for stops the walk without a finding.
    """
    current: Any = start
    for index, segment in enumerate(segments):
        current = _unwrap(current)
        if segment == LIST_ITEM_SEGMENT:
            item_type = _list_item_type(current)
            if item_type is None:
                return None
            current = item_type
            continue
        if not isinstance(current, type) or not issubclass(current, BaseModel):
            return None
        if current.model_config.get("extra") == "allow":
            return None
        field_info = current.model_fields.get(segment)
        if field_info is not None:
            current = field_info.annotation
            continue
        if hasattr(current, segment):
            # A property or a method of the class: what it returns is not described, so the check stops.
            return None
        return index, current
    return None


def _describe_fields(model_class: type[BaseModel]) -> str:
    return ", ".join(model_class.model_fields) or "(none)"


def _check_path(*, path: TemplateFieldPath, inputs: InputStuffSpecs, pipe_code: str, label: str) -> None:
    stuff_spec = inputs.root.get(path.root)
    if stuff_spec is None or not path.segments:
        return
    if not stuff_spec.concept.declares_a_structure_class:
        # An `Anything` input declares no fields to check a path against; the strict undefined catches a bad read at the dry run.
        return
    content_class = get_class_registry().get_required_subclass(name=stuff_spec.concept.structure_class_name, base_class=StuffContent)
    first_segment = path.segments[0]
    if stuff_spec.is_multiple():
        # A list input iterates over its items, and otherwise reads as the list stuff itself.
        if first_segment == LIST_ITEM_SEGMENT:
            start: Any = list[content_class]  # type: ignore[valid-type]
        else:
            start = ListContent
    else:
        start = content_class
    if first_segment != LIST_ITEM_SEGMENT and (first_segment.startswith("_") or hasattr(StuffArtefact, first_segment)):
        is_content_field = isinstance(start, type) and issubclass(start, BaseModel) and first_segment in start.model_fields
        if not is_content_field:
            # The artefact's own accessors and metadata (`get`, `_stuff_name`), which templates may read too.
            return
    missing = _first_missing_field(start=start, segments=path.segments)
    if missing is None:
        return
    index, model_class = missing
    missing_field = path.segments[index]
    if index == 0:
        holder = f"the concept '{stuff_spec.concept.concept_ref}' of input '{path.root}'"
    else:
        holder = f"'{model_class.__name__}'"
    reached = ""
    loop_variable = path.written.split(".")[0]
    if loop_variable != path.root:
        iterated = ".".join(segment for segment in path.segments[:index] if segment != LIST_ITEM_SEGMENT)
        reached = f" ({loop_variable} is an item of {path.root}.{iterated})"
    msg = (
        f"PipeDocGen '{pipe_code}': the {label} reads '{path.written}'{reached}, but {holder} has no field '{missing_field}'. "
        f"Its fields are: {_describe_fields(model_class)}."
    )
    raise PipeDocGenFactoryError(msg)


def check_template_field_paths(
    *, pipe_code: str, template_source: str, template_category: TemplateCategory, label: str, inputs: InputStuffSpecs
) -> None:
    """Refuse a template that reads a field its input's concept does not have.

    Raises:
        PipeDocGenFactoryError: a path names a missing field.
    """
    for path in detect_template_field_paths(template_source=rewrite_template_sigils(template_source), template_category=template_category):
        _check_path(path=path, inputs=inputs, pipe_code=pipe_code, label=label)
