"""Resolve which Pydantic class a structured-generation leaf hands to the provider.

``ObjectAssignment`` is a wire model: it carries the output structure's JSON *schema*, never the live
class, because a distributed orchestrator ships it to a worker process that cannot receive a ``type``.
A worker entering from that boundary has to rebuild an approximation of the class from the schema —
which is lossy (``datamodel-code-generator`` cannot express a custom validator, and drops
``json_schema_extra`` format/pattern hints) and costs a code generation plus an ``exec()`` on the first
call for each distinct schema.

In-process there is no boundary: the caller's real class is still on the stack, so it travels down
beside the assignment and is used as-is. ``None`` means "no class in hand", which is exactly what a
worker entering from the boundary passes — so the distributed path keeps today's behaviour by
construction, with no flag to set.

The structured-*search* leaf has no nullable arm to resolve: its in-process entry point carries the
caller's class outright, and its boundary arm always rebuilds — it calls ``SchemaToModelFactory``
directly.
"""

from pydantic import BaseModel

from pipelex.cogt.content_generation.assignment_models import ObjectAssignment
from pipelex.cogt.content_generation.schema_to_model_factory import SchemaToModelFactory


def resolve_object_class(*, object_assignment: ObjectAssignment, object_class: type[BaseModel] | None) -> type[BaseModel]:
    """Return the caller's class when it is in hand, otherwise rebuild it from the assignment's schema."""
    if object_class is not None:
        return object_class
    return SchemaToModelFactory.make_from_json_schema(
        schema=object_assignment.object_class_schema,
        class_name=object_assignment.object_class_name,
    )
