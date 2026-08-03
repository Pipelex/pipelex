"""The `python-structures` projection and the runtime concept factory must read one declaration alike.

Both are faithful readings of the same authored `ConceptBlueprint`: `ConceptFactory` builds the class
an interpreted run stores in memory, `emit_python_structures` writes the class a consumer imports and
hands back to that same runtime. When they disagree about the **content class** a concept lands on,
nothing raises — the interpreter's text-vs-object dispatch just answers differently for the same
concept, and the text path's `model_validate({"text": ...})` succeeds on either class. So the gate is
the agreement itself: same nearest `StuffContent` ancestor, for every shape a concept can be authored in.

There are exactly four such shapes, and the enumeration is closed because MTHDS forbids `refines` and
`structure` together (`ConceptBlueprint.validate_refines_and_structure`) — the one combination where a
divergence could hide behind a structured concept refining a structureless one cannot be authored at all.
"""

from pathlib import Path
from typing import Any

import pytest

from pipelex.codegen.emitters.python_structures import emit_python_structures
from pipelex.codegen.resolved_concepts import resolve_concepts_from_crate
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.system.registries.class_registry_access import get_class_registry
from tests.unit.pipelex.codegen.conftest import CRATE_TEST_VERSION, load_generated_module

_DOMAIN = "parity"

# One authored source, read by both sides. Declaration order matters for the runtime reader only:
# `Refined` needs `Structured`'s generated class registered before it can refine it.
_AUTHORED: dict[str, ConceptBlueprint] = {
    # structureless — the shape the runtime promotes to a refinement of native Text.
    "Opaque": ConceptBlueprint(description="A concept described in prose and nothing else"),
    # structured
    "Structured": ConceptBlueprint(
        description="A concept with an explicit structure",
        structure={"note": ConceptStructureBlueprint(description="a note", type=ConceptStructureBlueprintFieldType.TEXT, required=True)},
    ),
    # refines a native
    "RefinesNative": ConceptBlueprint(description="A small image", refines="Image"),
    # refines an in-crate concept
    "Refined": ConceptBlueprint(description="A narrower structured concept", refines="Structured"),
}

_RUNTIME_CONTENT_PACKAGE = "pipelex.core.stuffs."


def _nearest_content_ancestor(concept_class: type[Any]) -> str:
    """The nearest ancestor that is a runtime content class — the vocabulary both readers share.

    Generated and projected classes are both anonymous to each other, so comparing them directly says
    nothing; what has to match is the runtime class each one bottoms out at.
    """
    for ancestor in concept_class.__mro__:
        if ancestor.__module__.startswith(_RUNTIME_CONTENT_PACKAGE):
            return ancestor.__name__
    msg = f"{concept_class.__name__} has no runtime content class in its MRO: {[base.__name__ for base in concept_class.__mro__]}"
    raise AssertionError(msg)


class TestProjectionAgreesWithRuntimeBase:
    @pytest.fixture
    def projected_module(self, tmp_path: Path) -> Any:
        authored = LibraryCrate(
            concepts={f"{_DOMAIN}.{code}": blueprint for code, blueprint in _AUTHORED.items()},
            domains={_DOMAIN: DomainBlueprint(code=_DOMAIN, description="Parity domain")},
        )
        crate = normalize_crate(authored, mthds_version=CRATE_TEST_VERSION)
        content = emit_python_structures(resolve_concepts_from_crate(crate))[0].content
        return load_generated_module(content, tmp_path=tmp_path, name="gen_structures_parity")

    @pytest.fixture
    def runtime_classes(self, load_empty_library: Any) -> dict[str, type[Any]]:
        load_empty_library()
        registry = get_class_registry()
        classes: dict[str, type[Any]] = {}
        for code, blueprint in _AUTHORED.items():
            concept = ConceptFactory.make_from_blueprint(domain_code=_DOMAIN, concept_code=code, blueprint_or_string_description=blueprint)
            classes[code] = registry.get_required_subclass(name=concept.structure_class_name, base_class=StuffContent)
        return classes

    @pytest.mark.parametrize("code", list(_AUTHORED))
    def test_both_readers_land_on_the_same_content_class(self, code: str, projected_module: Any, runtime_classes: dict[str, type[Any]]):
        projected: type[Any] = getattr(projected_module, code)
        assert _nearest_content_ancestor(projected) == _nearest_content_ancestor(runtime_classes[code])

    def test_structureless_lands_on_text_content(self, projected_module: Any, runtime_classes: dict[str, type[Any]]):
        """Name the answer, not just the agreement — the two could agree by both being wrong.

        `TextContent` is the runtime's reading: "describe it in prose and get text back" is what a
        structureless declaration means to an author today, and the interpreter's text-vs-object
        dispatch is what reads it back.
        """
        assert _nearest_content_ancestor(runtime_classes["Opaque"]) == "TextContent"
        assert _nearest_content_ancestor(projected_module.Opaque) == "TextContent"

    def test_python_class_backed_concept_keeps_the_root_base(self, tmp_path: Path):
        """The one structureless shape the projection must NOT promote.

        `structure = "<ClassName>"` names a hand-written Python class the crate cannot see, so its
        content class is genuinely unknown here — guessing `TextContent` would be the same defect in
        the other direction. The honest floor is the structurally valid root (B1-1).
        """
        authored = LibraryCrate(
            mthds_version=CRATE_TEST_VERSION,
            concepts={f"{_DOMAIN}.Legacy": ConceptBlueprint(description="python-backed", structure="MyLegacyClass")},
        )
        content = emit_python_structures(resolve_concepts_from_crate(authored))[0].content
        module = load_generated_module(content, tmp_path=tmp_path, name="gen_structures_parity_opaque_class")
        assert _nearest_content_ancestor(module.Legacy) == "StructuredContent"
