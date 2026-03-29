from typing import Any, cast

from kajson.exceptions import KajsonException
from pydantic import ValidationError

from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_content_factory import StuffContentFactory
from pipelex.hub import get_class_registry
from pipelex.pipe_run.exceptions import PipeJobError


def _hydrate_content(concept: Concept, raw_content: dict[str, Any] | str) -> StuffContent:
    """Hydrate a single StuffContent from a raw value.

    Handles both plain content and ListContent. When the raw value is a dict
    with an 'items' key containing a list, the content is deserialized as
    ListContent with each item validated as the concept's structure class.
    This is necessary because the concept's structure_class_name always refers
    to the *item* type, even when the stuff holds a list of those items.
    """
    if isinstance(raw_content, dict) and "items" in raw_content and isinstance(raw_content["items"], list):
        item_class = get_class_registry().get_required_subclass(name=concept.structure_class_name, base_class=StuffContent)
        raw_items = cast("list[dict[str, Any]]", raw_content["items"])
        items = [item_class.model_validate(raw_item) for raw_item in raw_items]
        return ListContent(items=items)

    return StuffContentFactory.make_stuff_content_from_concept_required(
        concept=concept,
        value=raw_content,
    )


def hydrate_working_memory(working_memory_raw: dict[str, Any]) -> WorkingMemory:
    """Reconstruct typed WorkingMemory from a raw dict.

    Must be called AFTER load_from_crate() has registered dynamic classes
    in the scoped ClassRegistry. Uses concept.structure_class_name to look up
    the correct StuffContent subclass from the registry.
    """
    working_memory = WorkingMemory()

    raw_root = working_memory_raw.get("root", {})
    for stuff_name, stuff_dict in raw_root.items():
        try:
            concept = Concept.model_validate(stuff_dict["concept"])
            content = _hydrate_content(concept=concept, raw_content=stuff_dict["content"])
            stuff = Stuff(
                stuff_code=stuff_dict["stuff_code"],
                stuff_name=stuff_dict.get("stuff_name"),
                concept=concept,
                content=content,
            )
        except KeyError as exc:
            msg = f"Failed to hydrate stuff '{stuff_name}': missing key {exc} in raw dict"
            raise PipeJobError(msg) from exc
        except (ValidationError, KajsonException) as exc:
            msg = f"Failed to hydrate stuff '{stuff_name}': {exc}"
            raise PipeJobError(msg) from exc
        working_memory.root[stuff_name] = stuff

    working_memory.aliases = working_memory_raw.get("aliases", {})
    return working_memory
