"""The model specs a model reference may be served by, read off the model deck as a run reads it.

Two callers need the same answer: run setup, which compares a file input with every model a consumer may reach, and the
step that converts an Office file, which hands the original only when every model that may serve reads it. Both read a
handle or an alias as its one model and a waterfall as every member, so a waterfall whose later member reads only PDFs
is never handed a Word file the setup check let through.
"""

from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.exceptions import ModelReferenceParseError
from pipelex.cogt.models.model_reference import ModelReference, ModelReferenceKind
from pipelex.runtime_hub import get_model_deck


def resolve_model_specs(*, model_reference: str, model_type: ModelType) -> list[InferenceModelSpec]:
    """The model specs a model reference can be served by: one for a handle or an alias, every available member for a waterfall.

    A preset is not resolved here: the caller resolves a step's choice to a setting first. A member
    the deck does not serve (its backend is disabled) is skipped, since no run could use it either.
    An unresolvable reference gives no spec.
    """
    return _resolve_model_specs(model_reference=model_reference, model_type=model_type, visited=frozenset())


def _resolve_model_specs(*, model_reference: str, model_type: ModelType, visited: frozenset[str]) -> list[InferenceModelSpec]:
    if model_reference in visited:
        return []
    visited |= {model_reference}
    try:
        reference = ModelReference.parse(model_reference)
    except ModelReferenceParseError:
        return []
    model_deck = get_model_deck()
    aliases, waterfalls = model_deck.get_aliases_and_waterfalls_for_type(model_type)
    alias_target: str | None = None
    waterfall_members: list[str] | None = None
    match reference.kind:
        case ModelReferenceKind.PRESET:
            return []
        case ModelReferenceKind.ALIAS:
            alias_target = aliases.get(reference.name)
        case ModelReferenceKind.WATERFALL:
            waterfall_members = waterfalls.get(reference.name)
        case ModelReferenceKind.HANDLE:
            # A handle served as another type only does not stop the lookup: this type's alias or
            # waterfall of the same name is tried next, as the deck's own lookup does.
            if model_spec := model_deck.inference_models.get(model_type=model_type, handle=reference.name):
                return [model_spec]
            alias_target = aliases.get(reference.name)
            waterfall_members = None if alias_target else waterfalls.get(reference.name)
    if alias_target:
        return _resolve_model_specs(model_reference=alias_target, model_type=model_type, visited=visited)
    model_specs: list[InferenceModelSpec] = []
    for member in waterfall_members or []:
        model_specs.extend(_resolve_model_specs(model_reference=member, model_type=model_type, visited=visited))
    return model_specs
