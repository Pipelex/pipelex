from typing import Any

from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content_factory import StuffContentFactory


def hydrate_working_memory(working_memory_raw: dict[str, Any]) -> WorkingMemory:
    """Reconstruct typed WorkingMemory from a raw dict.

    Must be called AFTER load_from_crate() has registered dynamic classes
    in the scoped ClassRegistry. Uses concept.structure_class_name to look up
    the correct StuffContent subclass from the registry.
    """
    working_memory = WorkingMemory()

    raw_root = working_memory_raw.get("root", {})
    for stuff_name, stuff_dict in raw_root.items():
        concept = Concept.model_validate(stuff_dict["concept"])
        content = StuffContentFactory.make_stuff_content_from_concept_required(
            concept=concept,
            value=stuff_dict["content"],
        )
        stuff = Stuff(
            stuff_code=stuff_dict["stuff_code"],
            stuff_name=stuff_dict.get("stuff_name"),
            concept=concept,
            content=content,
        )
        working_memory.root[stuff_name] = stuff

    working_memory.aliases = working_memory_raw.get("aliases", {})
    return working_memory
