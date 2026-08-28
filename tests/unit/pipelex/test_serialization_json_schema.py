"""No Pipelex model publishes an opaque serialization JSON Schema.

Pydantic derives a model's *serialization* schema from its `@model_serializer`'s return
annotation and prefers it over the schema it would generate. A `-> dict[str, Any]` therefore
replaces the real shape with `{"type": "object", "additionalProperties": true}` — no properties,
no `required`, no closed shape — while validation-mode schemas stay complete and every runtime
`model_dump()` keeps working. Nothing in this repo notices: the suite is green, and no call to
`model_json_schema()` in `pipelex/` asks for serialization mode (the MTHDS schema generator asks
for `mode="validation"` explicitly). The damage lands one repo away, in a consumer that generates
response-model schemas — FastAPI always does — where a whole blueprint reaches clients as an
opaque object and a client generator produces nothing useful from it.

The bug class already recurred: it hit four models here and the input-form field descriptors
upstream in `mthds`. Hence a sweep rather than four hand-written assertions — the next model to
grow a wrap serializer is caught the day it is written, not the next time a consumer regenerates
an artifact.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any, cast

import pytest
from pydantic import BaseModel
from pydantic.errors import PydanticInvalidForJsonSchema

import pipelex
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint
from pipelex.pipe_machinery.pipe_blueprint import InputSlotBlueprint
from pipelex.pipe_operators.compose.construct_blueprint import ConstructBlueprint

# The models that carry a `@model_serializer(mode="wrap")` and once published nothing because of it.
WRAP_SERIALIZER_MODELS = [
    ConceptBlueprint,
    ConceptStructureBlueprint,
    InputSlotBlueprint,
    ConstructBlueprint,
]

# `FuncRegistry` holds live callables, which have no JSON Schema at all — pydantic refuses to build
# one. Pinned by name rather than skipped silently: a model that newly stops being describable drops
# out of the sweep, and this is what makes that visible instead of quietly shrinking the guard.
MODELS_WITHOUT_A_JSON_SCHEMA = {
    "pipelex.system.registries.func_registry.FuncRegistry",
}

REMEDY = (
    "Drop the return annotation from the model's `@model_serializer` — pydantic turns it into the "
    "model's serialization JSON Schema and prefers it over the generated one."
)


def _import_every_pipelex_module() -> int:
    """Import every `pipelex.*` module and return how many loaded.

    Nothing is caught. A module that fails to import takes the sweep down with its own traceback,
    which is the root cause; recording it as a string and carrying on would both discard that
    traceback and leave the sweep running over a partially imported package — a guard gone quiet
    exactly where the tree got interesting.
    """
    imported = 0
    for module_info in pkgutil.walk_packages(pipelex.__path__, prefix=f"{pipelex.__name__}."):
        importlib.import_module(module_info.name)
        imported += 1
    return imported


def _discover_pipelex_models() -> list[type[BaseModel]]:
    """Every `BaseModel` subclass declared under `pipelex.`, after loading the whole package."""
    _import_every_pipelex_module()

    seen: set[type[BaseModel]] = set()

    def walk(cls: type[BaseModel]) -> None:
        for sub in cls.__subclasses__():
            if sub not in seen:
                seen.add(sub)
                walk(sub)

    walk(BaseModel)
    models = [cls for cls in seen if cls.__module__.startswith(f"{pipelex.__name__}.")]
    return sorted(models, key=lambda cls: f"{cls.__module__}.{cls.__qualname__}")


def _resolve_root(schema: dict[str, Any]) -> dict[str, Any]:
    """Follow a top-level `$ref` into `$defs`.

    A self-referential model (`ConstructBlueprint` nests itself) publishes `{"$defs": …, "$ref": …}`
    at the top, so reading `properties` off the raw schema would judge every recursive model opaque.
    """
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return schema
    definition_name = ref.rsplit("/", maxsplit=1)[-1]
    defs: dict[str, Any] = schema.get("$defs") or {}
    resolved: Any = defs.get(definition_name)
    if isinstance(resolved, dict):
        return cast("dict[str, Any]", resolved)
    return schema


def _is_opaque_object(schema: dict[str, Any]) -> bool:
    """The exact shape an erasing return annotation produces: an object that says nothing."""
    root = _resolve_root(schema)
    return root.get("type") == "object" and not root.get("properties") and root.get("additionalProperties") is True


def _erases_its_shape(model: type[BaseModel]) -> bool:
    """The model is opaque when serialized but not when validated — the erasure signature.

    Asymmetry is what makes this a defect rather than a fact. A model that is honestly open —
    `extra="allow"` with no declared fields (`CompositeContent`), or a `RootModel[dict[str, Any]]`
    (`SdkClientRegistry`) — is opaque in *both* modes, and an open dict really is its shape. Testing
    the asymmetry instead of the shape is what lets this sweep run without an allowlist to maintain,
    and an allowlist is the wrong instrument here anyway: it would have to be extended by the very
    person adding the next erasing serializer.
    """
    return _is_opaque_object(model.model_json_schema(mode="serialization")) and not _is_opaque_object(model.model_json_schema(mode="validation"))


def _sweep_serialization_shapes() -> dict[str, bool]:
    """Every describable Pipelex model, mapped to whether it erases its shape when serialized."""
    verdicts: dict[str, bool] = {}
    for model in _discover_pipelex_models():
        qualified_name = f"{model.__module__}.{model.__qualname__}"
        if qualified_name in MODELS_WITHOUT_A_JSON_SCHEMA:
            continue
        verdicts[qualified_name] = _erases_its_shape(model)
    return verdicts


def _models_without_a_json_schema() -> set[str]:
    """The models pydantic refuses to describe at all, discovered rather than assumed."""
    undescribable: set[str] = set()
    for model in _discover_pipelex_models():
        try:
            model.model_json_schema(mode="serialization")
        except PydanticInvalidForJsonSchema:
            undescribable.add(f"{model.__module__}.{model.__qualname__}")
    return undescribable


class TestSerializationJsonSchema:
    def test_discovery_is_not_vacuous(self) -> None:
        """Anti-vacuity: the walk really loaded the package and really found models.

        Deliberately not parametrized — pytest reports `got empty parameter set` and exits 0 on an
        empty list, so the guard would be unreachable exactly when it matters.
        """
        imported = _import_every_pipelex_module()
        assert imported, "No pipelex module imported — the sweep would compare two empty sets and pass vacuously."

        models = _discover_pipelex_models()
        assert models, "No pipelex BaseModel discovered — the sweep would pass vacuously."

        discovered_names = {cls.__qualname__ for cls in models}
        assert "ConceptBlueprint" in discovered_names, "The blueprint layer is missing from the sweep — discovery is not reaching the wire surface."

        assert _models_without_a_json_schema() == MODELS_WITHOUT_A_JSON_SCHEMA, (
            "The set of models pydantic cannot describe has moved. A model that newly stops being describable silently "
            "leaves the sweep below, so update MODELS_WITHOUT_A_JSON_SCHEMA deliberately — after checking the model "
            f"really has no wire form.\n  expected: {sorted(MODELS_WITHOUT_A_JSON_SCHEMA)}\n  actual:   {sorted(_models_without_a_json_schema())}"
        )

    def test_no_pipelex_model_publishes_an_opaque_serialization_schema(self) -> None:
        """A model whose serialization schema says nothing is invisible to every client generator."""
        offenders = [name for name, erased in _sweep_serialization_shapes().items() if erased]

        assert not offenders, (
            "These models describe themselves when validated but publish an opaque object when serialized:\n"
            + "\n".join(f"  - {name}" for name in offenders)
            + f"\n\n{REMEDY}"
        )

    @pytest.mark.parametrize("model", WRAP_SERIALIZER_MODELS, ids=lambda model: model.__qualname__)
    def test_wrap_serializer_models_keep_their_property_lists(self, model: type[BaseModel]) -> None:
        """Serialization mode describes the same fields as validation mode.

        Sharper than the opaque-shape sweep: it catches a *partial* erasure, where a schema keeps a
        property or two and loses the rest, which the sweep above would wave through.
        """
        serialization_properties = sorted(_resolve_root(model.model_json_schema(mode="serialization")).get("properties", {}))
        validation_properties = sorted(_resolve_root(model.model_json_schema(mode="validation")).get("properties", {}))

        assert serialization_properties, f"{model.__qualname__} publishes no properties in serialization mode. {REMEDY}"
        assert serialization_properties == validation_properties, (
            f"{model.__qualname__} describes different fields depending on the schema mode.\n"
            f"  serialization: {serialization_properties}\n"
            f"  validation:    {validation_properties}\n\n{REMEDY}"
        )
