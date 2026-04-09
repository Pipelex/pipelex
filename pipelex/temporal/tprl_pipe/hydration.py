from typing import Any, cast

from kajson.exceptions import KajsonException
from pydantic import ValidationError

from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_content_factory import StuffContentFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_class_registry
from pipelex.pipe_run.exceptions import PipeJobError


def _hydrate_list_item(raw_item: dict[str, Any] | str) -> StuffContent:
    """Hydrate a single list item for Anything[] results.

    Tries __class__ metadata first, falls back to TextContent for plain text or
    dicts with a 'text' key (the common case for Anything outputs).
    """
    if isinstance(raw_item, str):
        return TextContent(text=raw_item)

    class_name = raw_item.get("__class__")
    if class_name is not None:
        item_class = get_class_registry().get_required_subclass(name=class_name, base_class=StuffContent)
        clean_item = {key: val for key, val in raw_item.items() if key not in {"__class__", "__module__"}}
        return cast("StuffContent", item_class.model_validate(clean_item))

    # No __class__ metadata — fall back to TextContent (the common Anything case)
    if "text" in raw_item:
        return TextContent.model_validate(raw_item)

    msg = f"Cannot hydrate Anything list item: no __class__ metadata and not a TextContent dict. Keys: {list(raw_item.keys())}"
    raise PipeJobError(msg)


def _hydrate_content(concept: Concept, raw_content: list[Any] | dict[str, Any] | str) -> StuffContent:
    """Hydrate a single StuffContent from a raw value.

    Handles both plain content and ListContent.  The Temporal serialization
    format (produced by ``WorkingMemory.dump_for_temporal()``) encodes
    ListContent as a plain JSON list and single StuffContent as a dict,
    so the type check is unambiguous — no heuristic required.

    The concept's ``structure_class_name`` always refers to the *item* type,
    even when the stuff holds a list of those items.
    """
    if isinstance(raw_content, list):
        registry = get_class_registry()
        item_class_or_none = registry.get_class(name=concept.structure_class_name)
        if item_class_or_none is not None and issubclass(item_class_or_none, StuffContent):
            # Known content class (e.g. TextContent, PageContent)
            raw_items = cast("list[dict[str, Any]]", raw_content)
            items = [item_class_or_none.model_validate(raw_item) for raw_item in raw_items]
        else:
            # Anything or unknown concept — resolve each item by its embedded type metadata
            raw_items = cast("list[dict[str, Any]]", raw_content)
            items = [_hydrate_list_item(raw_item) for raw_item in raw_items]
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
