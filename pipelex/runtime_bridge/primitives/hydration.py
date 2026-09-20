from typing import Any, cast

from kajson.exceptions import KajsonException
from pydantic import ValidationError

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_provider_abstract import ConceptProviderAbstract
from pipelex.core.concepts.exceptions import ConceptLibraryConceptNotFoundError, ConceptRefAmbiguousError
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.absence import AbsenceRecord
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.qualified_ref import QualifiedRef, QualifiedRefError
from pipelex.core.stuffs.composite_content import CompositeContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_content_factory import StuffContentFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_concept_library, get_current_library_id_or_none
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.libraries.exceptions import LibraryError
from pipelex.pipe_run.exceptions import PipeJobError
from pipelex.runtime_hub import get_class_registry


def _validate_as_known_class(*, item_class: type[StuffContent], raw_item: StuffContent | dict[str, Any]) -> StuffContent:
    """Validate raw_item into item_class, tolerating cross-exec instances.

    The transport format ships ListContent items as plain dicts with
    pipelex-private ``__pipelex_class__`` / ``__pipelex_module__`` markers
    (see ``WorkingMemory.dump_for_transport``), so kajson never eagerly rehydrates
    them — the ``isinstance(raw_item, StuffContent)`` branch below is defensive,
    kept for callers that pass already-typed instances and for any path where
    kajson might produce an instance whose class identity drifted across execs.
    In that drift case, ``model_validate`` would reject the old instance because
    ``type(raw_item) is not item_class``, so we round-trip through
    ``smart_dump()`` (serialize_as_any) to let nested subclass fields survive.
    """
    if isinstance(raw_item, StuffContent):
        if type(raw_item) is item_class:
            return raw_item
        else:
            return item_class.model_validate(raw_item.smart_dump())
    else:
        return item_class.model_validate(raw_item)


def _hydrate_list_item(raw_item: dict[str, Any] | str | StuffContent) -> StuffContent:
    """Hydrate a single list item for Anything[] results.

    Resolves the item class from the pipelex-private ``__pipelex_class__`` /
    ``__pipelex_module__`` markers written by ``dump_for_transport``. Falls back
    to TextContent for plain text or dicts with a 'text' key (the common case
    for Anything outputs without explicit type metadata).
    """
    if isinstance(raw_item, str):
        return TextContent(text=raw_item)

    # Already hydrated by kajson via a transport data converter. The instance
    # may come from a previous exec of the dynamic source — normalize through
    # the registry's current class so downstream type checks stay consistent.
    if isinstance(raw_item, StuffContent):
        class_name_from_instance = type(raw_item).__name__
        item_class_or_none = get_class_registry().get_class(name=class_name_from_instance)
        if item_class_or_none is not None and issubclass(item_class_or_none, StuffContent):
            return _validate_as_known_class(item_class=item_class_or_none, raw_item=raw_item)
        return raw_item

    class_name = raw_item.get("__pipelex_class__")
    if class_name is not None:
        item_class = get_class_registry().get_required_subclass(name=class_name, base_class=StuffContent)
        clean_item = {key: val for key, val in raw_item.items() if key not in {"__pipelex_class__", "__pipelex_module__"}}
        return cast("StuffContent", item_class.model_validate(clean_item))

    # No __class__ metadata — fall back to TextContent for marker-less simple text dicts.
    if "text" in raw_item:
        return TextContent.model_validate(raw_item)

    msg = f"Cannot hydrate Anything list item: no __class__ metadata and no recognized content structure. Keys: {list(raw_item.keys())}"
    raise PipeJobError(msg)


def _hydrate_composite_component(raw_value: Any) -> Any:
    """Hydrate one component of a CompositeContent from its transport encoding.

    ``dump_for_transport`` encodes composite components with the same convention as
    the top level: a list value is a ListContent (marker-stamped item dicts), a dict
    value is a single StuffContent stamped with pipelex-private ``__pipelex_class__``
    / ``__pipelex_module__`` markers. Anything else (plain scalars, marker-less
    legacy payloads, instances already rebuilt by kajson) passes through unchanged —
    CompositeContent is untyped by design, so there is no concept to fall back on.
    """
    if isinstance(raw_value, list):
        raw_items = cast("list[dict[str, Any] | str | StuffContent]", raw_value)
        return ListContent(items=[_hydrate_list_item(raw_item) for raw_item in raw_items])
    if isinstance(raw_value, dict):
        raw_dict = cast("dict[str, Any]", raw_value)
        if "__pipelex_class__" in raw_dict:
            return _hydrate_list_item(raw_dict)
        return raw_dict
    return raw_value


def hydrate_content(raw_content: list[Any] | dict[str, Any] | str, *, concept: Concept) -> StuffContent:
    """Hydrate a single StuffContent from a raw value.

    Handles both plain content and ListContent.  The transport serialization
    format (produced by ``WorkingMemory.dump_for_transport()``) encodes
    ListContent as a plain JSON list and single StuffContent as a dict,
    so the type check is unambiguous — no heuristic required.  ListContent
    items carry pipelex-private ``__pipelex_class__`` / ``__pipelex_module__``
    markers so kajson's universal decoder leaves them alone in transit.

    The concept's ``structure_class_name`` always refers to the *item* type,
    even when the stuff holds a list of those items.
    """
    if isinstance(raw_content, list):
        registry = get_class_registry()
        item_class_or_none = registry.get_class(name=concept.structure_class_name)
        if item_class_or_none is not None and issubclass(item_class_or_none, StuffContent):
            # Known content class (e.g. TextContent, PageContent, or a dynamic
            # structured concept class). Use _validate_as_known_class so that
            # cross-exec instances rebuilt by kajson during cross-process transit
            # get normalized through a dict round-trip.
            items = [_validate_as_known_class(item_class=item_class_or_none, raw_item=raw_item) for raw_item in raw_content]
        else:
            # Anything or unknown concept — resolve each item by its embedded type metadata
            raw_items = cast("list[dict[str, Any]]", raw_content)
            items = [_hydrate_list_item(raw_item) for raw_item in raw_items]
        return ListContent(items=items)

    if isinstance(raw_content, dict):
        structure_class = get_class_registry().get_class(name=concept.structure_class_name)
        if structure_class is not None and issubclass(structure_class, CompositeContent):
            # Composite components carry their own class markers (extra="allow" fields
            # have no annotations to drive validation) — rebuild each one before
            # validating the composite, so typed access survives transport.
            components = {component_name: _hydrate_composite_component(raw_value) for component_name, raw_value in raw_content.items()}
            return structure_class.model_validate(components)

    return StuffContentFactory.make_stuff_content_from_concept_required(
        concept=concept,
        value=raw_content,
    )


def _resolve_native_stuff_concept(*, concept_ref: str, stuff_name: str) -> Concept:
    """Resolve a transported stuff's concept ref with the pinned native set alone.

    A reader outside any library scope is a live path, not a fixture: ``Pipelex.make()`` sets no
    current library, and on the transport boundary ``scoped_library_for_crate(None, …)`` is a true
    no-op that falls back to the active class registry. What such a reader can honestly answer is
    the native set, which the runtime pins and no bundle declares — the same answer
    ``DeliveryExecutor._resolve_concept_locally`` gives in the same situation. A ref a bundle
    declares is refused by name instead, because only a loaded library holds its definition.

    Raises:
        PipeJobError: the ref is malformed, or names a non-native concept.
    """
    try:
        is_native_ref = NativeConceptCode.is_valid_native_concept_ref(concept_ref=concept_ref)
    except QualifiedRefError as exc:
        msg = f"Failed to hydrate stuff '{stuff_name}': '{concept_ref}' is not a valid concept ref: {exc}"
        raise PipeJobError(msg) from exc
    if not is_native_ref:
        msg = (
            f"Failed to hydrate stuff '{stuff_name}': concept '{concept_ref}' is not native and no library is current — "
            "a stuff whose concept a bundle declares can only be hydrated against the loaded library that declares it"
        )
        raise PipeJobError(msg)
    native_code = QualifiedRef.parse(concept_ref).local_code
    return ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode(native_code))


def resolve_stuff_concept(*, concept_ref: Any, stuff_name: str, concept_provider: ConceptProviderAbstract | None) -> Concept:
    """Resolve the concept a transported stuff names.

    On the wire a stuff carries ``"concept": "<domain>.<Code>"`` and no definition — the
    standard's form, which ``StuffAbstract`` emits on every dump — so the definition, the
    ``structure_class_name`` above all, comes from the concept library the method loaded, the
    way the input side resolves an input envelope's ``concept``. Anything but a string is
    refused: the full-object form the runtime once dumped is not a shape a reader accepts.

    ``concept_provider`` is ``None`` when no library is current, and the native set then answers
    on its own — see :func:`_resolve_native_stuff_concept`. With a provider, the shared rule on
    :meth:`ConceptProviderAbstract.resolve_wire_concept_ref` decides, so a concept a dependency
    package contributed resolves through its aliased entry and a spelling two packages share is
    refused rather than bound to whichever one the reader happened to reach first.

    Raises:
        PipeJobError: ``concept_ref`` is not a string, names no concept of the library, or names
            a spelling the library holds more than once.
    """
    if not isinstance(concept_ref, str):
        msg = f"Failed to hydrate stuff '{stuff_name}': 'concept' must be the concept ref string '<domain>.<Code>', got {type(concept_ref).__name__}"
        raise PipeJobError(msg)
    if concept_provider is None:
        return _resolve_native_stuff_concept(concept_ref=concept_ref, stuff_name=stuff_name)
    try:
        return concept_provider.resolve_wire_concept_ref(concept_ref=concept_ref)
    except ConceptRefAmbiguousError as exc:
        msg = f"Failed to hydrate stuff '{stuff_name}': {exc}"
        raise PipeJobError(msg) from exc
    except (ConceptLibraryError, ConceptLibraryConceptNotFoundError) as exc:
        msg = f"Failed to hydrate stuff '{stuff_name}': concept '{concept_ref}' is not in the loaded library: {exc}"
        raise PipeJobError(msg) from exc


def hydrate_working_memory(working_memory_raw: dict[str, Any]) -> WorkingMemory:
    """Reconstruct typed WorkingMemory from its transport dump.

    A stuff on the wire names its concept and carries no definition, so each ref is resolved
    through the concept library of the current library when there is one: ``load_from_crate()``
    declares the concepts and registers the dynamic classes in one move, and the resolved
    concept's ``structure_class_name`` is then looked up in the scoped ClassRegistry to pick the
    StuffContent subclass.

    A current library is not a precondition, because a caller legitimately has none — ``Pipelex.make()``
    sets no current library, and the transport boundary's ``scoped_library_for_crate(None, …)`` is a
    documented no-op that falls back to the active class registry. Such a reader resolves the native
    refs from the pinned native set and refuses anything a bundle declares, naming the stuff.

    The absence ledger round-trips too: a recorded absence must survive cross-process
    transit, or a resolved-as-absent slot would degrade to a hard miss on the other side.
    """
    try:
        concept_provider: ConceptProviderAbstract | None = get_concept_library() if get_current_library_id_or_none() is not None else None
    except (LibraryError, RuntimeError) as exc:
        # The contextvar naming a library is not the same fact as that library still being there.
        # Whichever way it went, this function answers with PipeJobError and never with a raw one.
        msg = f"Failed to hydrate the working memory: the current library is no longer reachable: {exc}"
        raise PipeJobError(msg) from exc
    working_memory = WorkingMemory()

    raw_root = working_memory_raw.get("root", {})
    for stuff_name, stuff_dict in raw_root.items():
        try:
            concept = resolve_stuff_concept(concept_ref=stuff_dict["concept"], stuff_name=stuff_name, concept_provider=concept_provider)
            content = hydrate_content(concept=concept, raw_content=stuff_dict["content"])
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

    raw_absences: dict[str, Any] = working_memory_raw.get("absences", {})
    for absence_name, absence_raw in raw_absences.items():
        try:
            working_memory.absences[absence_name] = AbsenceRecord.model_validate(absence_raw)
        except ValidationError as exc:
            msg = f"Failed to hydrate absence record '{absence_name}': {exc}"
            raise PipeJobError(msg) from exc

    return working_memory
