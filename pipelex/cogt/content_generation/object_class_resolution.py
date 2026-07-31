"""Resolve which Pydantic class a structured-generation leaf hands to the provider.

``ObjectAssignment`` and its structured-search sibling are wire models: they carry the output structure's
JSON *schema*, never the live class, because a distributed orchestrator ships them to a worker process
that cannot receive a ``type``.
A worker entering from that boundary has to rebuild an approximation of the class from the schema —
which is lossy (``datamodel-code-generator`` cannot express a custom validator, and drops
``json_schema_extra`` format/pattern hints) and costs a code generation plus an ``exec()`` on the first
call for each distinct schema.

In-process there is no boundary: the caller's real class is still on the stack, so it travels down
beside the assignment and is used as-is. ``None`` means "no class in hand", which is exactly what a
worker entering from the boundary passes — so the distributed path keeps today's behaviour by
construction, with no flag to set.
"""

from typing import Any

from pydantic import BaseModel

from pipelex.cogt.content_generation.assignment_models import ObjectAssignment, SearchObjectAssignment
from pipelex.cogt.content_generation.schema_to_model_factory import SchemaToModelFactory


def resolve_object_class(*, object_assignment: ObjectAssignment, object_class: type[BaseModel] | None) -> type[BaseModel]:
    """Return the caller's class when it is in hand, otherwise rebuild it from the assignment's schema."""
    return _resolve_class(
        live_class=object_class,
        class_name=object_assignment.object_class_name,
        class_schema=object_assignment.object_class_schema,
    )


def resolve_search_output_class(*, search_object_assignment: SearchObjectAssignment, output_class: type[BaseModel] | None) -> type[BaseModel]:
    """Structured-search counterpart of :func:`resolve_object_class`.

    Same two arms, same meaning for ``None`` — the search assignment just names the two wire fields
    differently, which is not a reason for a second rebuild.
    """
    return _resolve_class(
        live_class=output_class,
        class_name=search_object_assignment.output_class_name,
        class_schema=search_object_assignment.output_class_schema,
    )


def _resolve_class(*, live_class: type[BaseModel] | None, class_name: str, class_schema: dict[str, Any]) -> type[BaseModel]:
    if live_class is not None:
        return live_class
    return SchemaToModelFactory.make_from_json_schema(
        schema=class_schema,
        class_name=class_name,
    )
