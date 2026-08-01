"""Convert a structured-generation leaf's result into the caller's own class.

The return leg of :mod:`.object_class_resolution`: that module decides which class travels *down* to
the provider, this one decides what comes back *up* to the caller. Both implementations of
``ContentGeneratorProtocol`` need it — the in-process generator here and the workflow arm of our
distributed-execution plugin, which lives in another repo and so cannot reach a ``_``-private helper.
That is why these are public: one home for the ``isinstance``-not-``type`` reasoning and for the dry-run
fidelity-error contract, instead of two copies that only agree until someone edits one.

The two entry points differ by what the leaf handed back: an object (the LLM leaves) or already
serialized data (the structured-search leaf, whose dict-out contract is what keeps a dynamic class
off a distributed orchestrator's wire).
"""

from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from pipelex.cogt.content_generation.exceptions import DryRunObjectFidelityError
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


def revalidate_leaf_object(
    raw_obj: BaseModel,
    *,
    object_class: type[BaseModelTypeVar],
    is_mock_built: bool,
    dump_mode: Literal["json", "python"] = "python",
) -> BaseModelTypeVar:
    """Convert a leaf-generated object into ``object_class``, unless it already is one.

    On the in-process path the leaf worked from ``object_class``, so the object is already one — note
    ``isinstance``, not ``type(...) is``: instructor does not hand back the class you gave it, it hands
    back ``create_model(cls.__name__, __base__=(cls, OpenAISchema))``, a *subclass*. Either way it needs
    no conversion — and re-validating it would run the caller's validators a **second** time, on data
    they already normalized. A validator that transforms rather than merely rejects (``f"INV-{value}"``, a
    list that gets a default appended) would corrupt its own output, and one that asserts its input is
    not yet normalized would reject valid provider output. Returning it untouched is what makes the
    caller's validator constrain the provider exactly once, which is the whole point of handing the live
    class down.

    The conversion is still needed at the *boundary*: a leaf that ran on a worker holding only the
    serialized assignment returns a plain ``BaseModel`` reconstructed from the JSON schema — never a
    subclass of ``object_class`` — so re-validating its data makes the result the proper subtype (e.g.
    ``StructuredContent``) the caller expects. The short-circuit never fires there today, and carrying it
    anyway is the point of sharing this: a boundary that ever *does* hand back the caller's real class
    (a local activity, an in-process shortcut, a converter change) cannot silently reinstate the double
    validation.

    ``by_alias=True`` is load-bearing, not cosmetic. The object being converted was built from
    ``object_class.model_json_schema()``, which pydantic emits **by alias**, so the schema's property
    names are what ``object_class`` accepts on the way back in. The rebuilt class does not always name
    its fields that way: ``datamodel-code-generator`` renames any property that is not a usable field
    name — a python keyword, or a name shadowing a ``BaseModel`` attribute (``json``, ``copy``,
    ``schema``, ``construct``) — and records the original as an alias. Dumping by field name then emits
    ``construct_`` for a field ``object_class`` calls ``construct``, and re-validation fails with a bare
    "Field required". Dumping by alias emits exactly the schema's property names, which is what the whole
    round trip is keyed on. Where nothing was renamed the alias *is* the field name, so this changes
    nothing for the models that were already fine.

    ``dump_mode`` is the one thing the two boundaries genuinely disagree on. It is
    :meth:`~pydantic.BaseModel.model_dump`'s own mode: an object that crossed a distributed
    orchestrator's payload boundary needs ``"json"``, because some field types only round-trip cleanly
    through their json form. In-process the default ``"python"`` is deliberate and must stay: json mode
    coerces values (``datetime`` → ``str`` and back), and there is no reason to pay that on a path that
    never left the process.

    ``is_mock_built`` carries the dry-run fidelity contract — see :func:`revalidate_leaf_data`.
    """
    if isinstance(raw_obj, object_class):
        return raw_obj
    return revalidate_leaf_data(
        raw_obj.model_dump(mode=dump_mode, serialize_as_any=True, by_alias=True),
        object_class=object_class,
        is_mock_built=is_mock_built,
    )


def revalidate_leaf_data(
    raw_data: dict[str, Any],
    *,
    object_class: type[BaseModelTypeVar],
    is_mock_built: bool,
) -> BaseModelTypeVar:
    """Validate already-serialized leaf data into ``object_class``, with the dry-run fidelity guard.

    Data is never an instance of anything, so there is no short-circuit to make: this validation is the
    single one on its path, and the caller's validators run here exactly once.

    Under the dry-run leaf mock (``run_mode=DRY``) the data was built from a class reconstructed from the
    JSON schema, which can drop invariants the original class enforces (custom validators,
    ``json_schema_extra`` format/pattern hints datamodel-code-generator omits on round-trip), so
    polyfactory can fill a value the reconstructed class accepts but the original rejects. Set
    ``is_mock_built`` on that path and the ``ValidationError`` is re-raised as a clear typed
    :class:`DryRunObjectFidelityError` naming the class and the ``examples`` / ``mock_format`` remedy.
    That gap cannot occur when the mock was built from the real class — an unsatisfiable invariant fails
    earlier and louder, as ``DryRunMockBuildError`` out of ``build_mock_object``. The guard is scoped to
    the dry path only: a LIVE provider's invalid output keeps its existing ``ValidationError``.
    """
    try:
        return object_class.model_validate(raw_data)
    except ValidationError as exc:
        if is_mock_built:
            raise DryRunObjectFidelityError.for_object_class(object_class.__name__) from exc
        raise
