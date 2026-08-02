"""Memory write-back, shared by every operator's kernel ops.

Each operator ends the same way — wrap the produced content in a `Stuff` and make it the memory's new
main stuff — so that ending lives here once rather than at each domain's ops module. It is also where
the memory contract is actually implemented, which is why a domain module never inlines the two calls:
the day the contract stops aliasing argument and return, exactly one function changes.
"""

from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory


def store_result(
    *,
    memory: WorkingMemory,
    concept: Concept,
    content: StuffContent,
    result_name: str | None = None,
    result_code: str | None = None,
) -> WorkingMemory:
    """Write a produced content into memory as the new main stuff, and return the memory.

    Returning it is the contract, not a convenience: the argument is mutated today because inline
    execution aliases the two, and a caller that relies on that aliasing breaks the moment a
    serialization boundary sits between them.
    """
    stuff = StuffFactory.make_stuff(concept=concept, content=content, name=result_name, code=result_code)
    memory.set_new_main_stuff(stuff=stuff, name=result_name)
    return memory
