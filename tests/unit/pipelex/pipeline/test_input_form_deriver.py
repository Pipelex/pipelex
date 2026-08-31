"""Unit-pin the deriver's escape hatches that the library loader keeps out of reach.

The loader rejects concept cycles (`LibraryLoadingError`), a `structure = "ClassName"` naming an
unregistered class, and a registered class that holds itself (which it reads as a concept cycle),
before a bundle ever reaches `build_input_form` — so those branches are exercised directly on a
hand-built qualified crate: the derivation must stay total and finite on any crate.
"""

from __future__ import annotations

from pydantic import Field, RootModel

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.pipeline.input_form import FieldKind, InputFormDeriver
from pipelex.system.registries.class_registry_access import get_class_registry
from tests.helpers.input_form import as_list, as_object, fields_by_name


class SelfReferentialPayload(StructuredContent):
    """A registered structure class that holds itself — reflection must cut the path, not recurse forever."""

    label: str = Field(description="The label")
    child: "SelfReferentialPayload | None" = Field(default=None, description="The nested twin")


class RootBackedTags(RootModel[list[str]]):
    """A `RootModel` field: the value on the wire IS the root list, never an object over a `root` key."""


class RootBackedPayload(StructuredContent):
    """A registered structure class holding a `RootModel` field."""

    label: str = Field(description="The label")
    tags: RootBackedTags = Field(description="The tags")


# mypy reads the two bases' `model_construct` overloads as incompatible; pydantic builds these classes
# fine and pyright accepts them, and a class-backed concept over a `RootModel` is what these tests pin.
class RootBackedSlug(StructuredContent, RootModel[str]):  # type: ignore[misc]
    """A registered structure class that IS a `RootModel` — the concept's whole payload is the root string."""


class RootBackedTagList(StructuredContent, RootModel[list[str]]):  # type: ignore[misc]
    """A registered structure class that IS a `RootModel` over a list — the payload is the list itself."""


def _concept_field(*, concept_ref: str) -> ConceptStructureBlueprint:
    return ConceptStructureBlueprint(description="link", type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref=concept_ref)


class TestInputFormDeriverEscapeHatches:
    def test_cycle_guard_emits_unknown_on_revisit(self) -> None:
        """A concept path that revisits a ref stops at an `unknown` node carrying the ref — finite, never recursive."""
        concepts: dict[str, ConceptBlueprint | str] = {
            "demo.Node": ConceptBlueprint(
                description="A node",
                structure={"label": "The label", "child": _concept_field(concept_ref="demo.Node")},
            ),
        }
        node = InputFormDeriver(concepts=concepts).derive_concept(name="root", concept_ref="demo.Node")

        child = as_object(node).fields[1]
        assert child.name == "child"
        assert child.kind == FieldKind.UNKNOWN
        assert child.concept_ref == "demo.Node"

    def test_indirect_cycle_is_cut_at_the_revisit(self) -> None:
        concepts: dict[str, ConceptBlueprint | str] = {
            "demo.Left": ConceptBlueprint(description="Left", structure={"right": _concept_field(concept_ref="demo.Right")}),
            "demo.Right": ConceptBlueprint(description="Right", structure={"left": _concept_field(concept_ref="demo.Left")}),
        }
        left = InputFormDeriver(concepts=concepts).derive_concept(name="left", concept_ref="demo.Left")

        right = as_object(as_object(left).fields[0])
        assert right.fields[0].kind == FieldKind.UNKNOWN
        assert right.fields[0].concept_ref == "demo.Left"

    def test_unregistered_class_backed_concept_is_unknown(self) -> None:
        """With no class to reflect, the node keeps its identity and description and reports `unknown`."""
        concepts: dict[str, ConceptBlueprint | str] = {
            "demo.Ghost": ConceptBlueprint(description="Backed by a class nobody registered", structure="NoSuchRegisteredClass"),
        }
        ghost = InputFormDeriver(concepts=concepts).derive_concept(name="ghost", concept_ref="demo.Ghost")

        assert ghost.kind == FieldKind.UNKNOWN
        assert ghost.concept_ref == "demo.Ghost"
        assert ghost.description == "Backed by a class nobody registered"

    def test_concept_absent_from_the_crate_is_unknown_without_a_class(self) -> None:
        """A slot typed with a concept the crate never saw (a `library_dirs` load) still gets a descriptor."""
        missing = InputFormDeriver(concepts={}).derive_concept(name="missing", concept_ref="elsewhere.Missing")

        assert missing.kind == FieldKind.UNKNOWN
        assert missing.concept_ref == "elsewhere.Missing"

    def test_chain_ending_at_a_base_absent_from_the_crate_is_unknown(self) -> None:
        """A cross-package `alias->…` base never enters the crate, so its shape is unknown — never prose."""
        concepts: dict[str, ConceptBlueprint | str] = {
            "demo.RefinedScore": ConceptBlueprint(description="Refines a dependency's score", refines="dep->other.Score"),
        }
        node = InputFormDeriver(concepts=concepts).derive_concept(name="score", concept_ref="demo.RefinedScore")

        assert node.kind == FieldKind.UNKNOWN
        assert node.refines == ["dep->other.Score"]
        assert node.description == "Refines a dependency's score"

    def test_a_self_referential_class_is_cut_at_the_revisit(self) -> None:
        """Class reflection terminates: the position that revisits the class is `unknown`, its siblings stated."""
        concepts: dict[str, ConceptBlueprint | str] = {
            "demo.Recursive": ConceptBlueprint(description="Backed by a class that holds itself", structure="SelfReferentialPayload"),
        }
        registry = get_class_registry()
        registry.register_class(SelfReferentialPayload)
        try:
            node = InputFormDeriver(concepts=concepts).derive_concept(name="recursive", concept_ref="demo.Recursive")
        finally:
            registry.unregister_class(SelfReferentialPayload)

        assert node.kind == FieldKind.OBJECT
        by_name = fields_by_name(node)
        assert by_name["label"].kind == FieldKind.TEXT
        assert by_name["child"].kind == FieldKind.UNKNOWN
        assert by_name["child"].required is False, "The self-reference is optional, and cutting the path does not change that"

    def test_a_root_model_field_reports_its_root_annotation(self) -> None:
        """A `RootModel` is its root value on the wire, so the node is the root's — never an `object` over `root`."""
        concepts: dict[str, ConceptBlueprint | str] = {
            "demo.RootBacked": ConceptBlueprint(description="Backed by a class holding a RootModel", structure="RootBackedPayload"),
        }
        registry = get_class_registry()
        registry.register_class(RootBackedPayload)
        try:
            node = InputFormDeriver(concepts=concepts).derive_concept(name="root_backed", concept_ref="demo.RootBacked")
        finally:
            registry.unregister_class(RootBackedPayload)

        by_name = fields_by_name(node)
        assert by_name["label"].kind == FieldKind.TEXT
        tags = as_list(by_name["tags"])
        assert tags.item.kind == FieldKind.TEXT
        assert tags.description == "The tags", "The field's own description survives the root reflection"

    def test_a_root_model_backed_concept_reports_its_root_annotation(self) -> None:
        """A class-backed concept whose class IS a `RootModel` states the root's node, never an `object` over `root`."""
        concepts: dict[str, ConceptBlueprint | str] = {
            "demo.Slug": ConceptBlueprint(description="A slug", structure="RootBackedSlug"),
        }
        registry = get_class_registry()
        registry.register_class(RootBackedSlug)
        try:
            node = InputFormDeriver(concepts=concepts).derive_concept(name="slug", concept_ref="demo.Slug")
        finally:
            registry.unregister_class(RootBackedSlug)

        assert node.kind == FieldKind.TEXT, "The payload `model_validate` accepts is the root string itself"
        assert node.concept_ref == "demo.Slug", "A top-level field states the concept it carries"
        assert node.description == "A slug"

    def test_a_root_model_backed_concept_over_a_list_is_a_list_node(self) -> None:
        """The root annotation decides the kind: a list root is a `list` node carrying the concept's own ref."""
        concepts: dict[str, ConceptBlueprint | str] = {
            "demo.TagList": ConceptBlueprint(description="The tags", structure="RootBackedTagList"),
        }
        registry = get_class_registry()
        registry.register_class(RootBackedTagList)
        try:
            node = InputFormDeriver(concepts=concepts).derive_concept(name="tag_list", concept_ref="demo.TagList")
        finally:
            registry.unregister_class(RootBackedTagList)

        tag_list = as_list(node)
        assert tag_list.item.kind == FieldKind.TEXT
        assert tag_list.concept_ref == "demo.TagList", "A root-valued concept IS the whole value, so its ref rides the list node"
        assert tag_list.description == "The tags"
