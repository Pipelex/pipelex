"""The GraphSpec io item a pipe run writes for a stuff it holds.

Every site that records a stuff on a graph node (a pipe's declared inputs at its start, its main
output at its end, a lifted pipe's plural companion slots, a parallel's branch outputs) builds the
item here, so what the item says about the stuff, its multiplicity above all, cannot drift between
them. Both graph builders read these items as they were written: the in-process `GraphTracer`
directly, and the event-replay `GraphSpecAssembler` through the trace events that carry them whole.
"""

from typing import TYPE_CHECKING, Any

from pipelex.graph.graphspec import IOSpec

if TYPE_CHECKING:
    from pipelex.core.stuffs.stuff import Stuff


def make_stuff_io_spec(*, name: str, stuff: "Stuff", include_data: bool, extra: dict[str, Any] | None = None) -> IOSpec:
    """Build the io item for `stuff`, recorded on its node under `name`.

    Args:
        name: The variable name the node knows the stuff by.
        stuff: The stuff itself, as the run holds it.
        include_data: Whether to embed the stuff's full serialized content (full data capture).
        extra: Extra markers for the item, such as the optional-output marker.
    """
    return IOSpec(
        name=name,
        concept=stuff.concept.code,
        content_type=stuff.content.content_type,
        digest=stuff.stuff_code,
        data=stuff.content.smart_dump() if include_data else None,
        multiplicity=stuff_io_multiplicity(stuff=stuff),
        extra=extra or {},
    )


def stuff_io_multiplicity(*, stuff: "Stuff") -> bool | None:
    """The multiplicity an io item records for `stuff`: `True` for a list, `None` for a single value.

    It is read off the value, not off any declaration: by the time a stuff exists the runtime has
    applied every rule that decides whether it is a list (a batch's item is single and its
    aggregate a list, a lifted plural output an empty list, a step run with `nb_output` a list), so
    the value is the one reading that the producer and every consumer of a stuff agree on.

    Never the item count. A variable-length list that produced one item would read as single, and
    an empty one would write `0`, which a GraphSpec reader refuses. `True` is truthful for every list.
    """
    return True if stuff.is_list else None
