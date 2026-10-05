import datetime
from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.exceptions import ConceptStructureClassNotFoundError
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.libraries.concept.concept_library_abstract import ConceptLibraryAbstract
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.pipe_controllers.binding.binding_concept_resolvers import LibraryConceptWalkResolver
from pipelex.pipe_controllers.binding.binding_derivation import BindingRoot, BindingValueKind, ConceptShape, derive_binding
from pipelex.pipe_controllers.binding.exceptions import BindingPathUnresolvedError


class _HarbourRecord(StructuredContent):
    name: str


class _OrphanRecord(StructuredContent):
    label: str


class _VesselRecord(StructuredContent):
    name: str
    tonnage: float
    crew: int
    is_moored: bool
    arrived_on: datetime.date
    arrived_at: datetime.datetime
    tide: datetime.time
    papers: dict[str, str]
    home_port: _HarbourRecord
    ports_of_call: list[_HarbourRecord]
    cargo: list[str]
    flag: str | None = None
    stowaway: _OrphanRecord | None = None
    holds: list[Any]


def _concept(*, code: str, structure_class_name: str, domain_code: str = "harbour", **kwargs: Any) -> Concept:
    return Concept(domain_code=domain_code, code=code, description=f"A {code}", structure_class_name=structure_class_name, **kwargs)


_CONCEPTS: dict[str, Concept] = {
    "harbour.Vessel": _concept(code="Vessel", structure_class_name="_VesselRecord"),
    "harbour.Harbour": _concept(code="Harbour", structure_class_name="_HarbourRecord"),
    "harbour.Berth": _concept(
        code="Berth",
        structure_class_name="harbour__Berth",
        declared_structure={"number": ConceptStructureBlueprint(description="The berth number", type=ConceptStructureBlueprintFieldType.INTEGER)},
    ),
    "harbour.GuestBerth": _concept(code="GuestBerth", structure_class_name="harbour__Berth", refines="Berth"),
    "harbour.Lost": _concept(code="Lost", structure_class_name="NoSuchClass"),
}
_CLASSES: dict[str, type[StuffContent]] = {"_VesselRecord": _VesselRecord, "_HarbourRecord": _HarbourRecord}


@pytest.fixture
def resolver(mocker: MockerFixture) -> LibraryConceptWalkResolver:
    concept_library = mocker.MagicMock(spec=ConceptLibraryAbstract)

    def get_required_concept(concept_ref: str) -> Concept:
        if concept_ref in _CONCEPTS:
            return _CONCEPTS[concept_ref]
        if concept_ref == "native.Page":
            return _concept(code="Page", structure_class_name="PageContent", domain_code="native")
        msg = f"Concept '{concept_ref}' not found"
        raise ConceptLibraryError(msg)

    def get_structure_class(*, concept: Concept) -> type[StuffContent]:
        if concept.structure_class_name not in _CLASSES:
            msg = f"No class '{concept.structure_class_name}'"
            raise ConceptStructureClassNotFoundError(msg)
        return _CLASSES[concept.structure_class_name]

    concept_library.get_required_concept.side_effect = get_required_concept
    concept_library.get_structure_class.side_effect = get_structure_class
    concept_library.list_concepts.return_value = list(_CONCEPTS.values())
    return LibraryConceptWalkResolver(concept_library=concept_library)


class TestLibraryConceptWalkResolver:
    @pytest.mark.parametrize(
        ("field_name", "value_kind", "concept_ref", "is_list", "may_hold_nothing"),
        [
            pytest.param("name", BindingValueKind.TEXT, None, False, False, id="str"),
            pytest.param("tonnage", BindingValueKind.NUMBER, None, False, False, id="float"),
            pytest.param("crew", BindingValueKind.NUMBER, None, False, False, id="int"),
            pytest.param("is_moored", BindingValueKind.YES_NO, None, False, False, id="bool"),
            pytest.param("arrived_on", BindingValueKind.DATE, None, False, False, id="date"),
            pytest.param("arrived_at", BindingValueKind.DATETIME, None, False, False, id="datetime"),
            pytest.param("tide", BindingValueKind.TIME, None, False, False, id="time"),
            pytest.param("papers", BindingValueKind.JSON, None, False, False, id="dict"),
            pytest.param("home_port", BindingValueKind.CONCEPT, "harbour.Harbour", False, False, id="content-class-of-one-concept"),
            pytest.param("ports_of_call", BindingValueKind.CONCEPT, "harbour.Harbour", True, False, id="list-of-content-class"),
            pytest.param("cargo", BindingValueKind.TEXT, None, True, False, id="list-of-str"),
            pytest.param("flag", BindingValueKind.TEXT, None, False, True, id="optional-str"),
            pytest.param("stowaway", BindingValueKind.UNDERIVABLE, None, False, True, id="content-class-of-no-concept"),
            pytest.param("holds", BindingValueKind.UNDERIVABLE, None, True, False, id="list-of-anything"),
        ],
    )
    def test_a_class_backed_concept_is_walked_through_its_class_fields(
        self,
        resolver: LibraryConceptWalkResolver,
        field_name: str,
        value_kind: BindingValueKind,
        concept_ref: str | None,
        is_list: bool,
        may_hold_nothing: bool,
    ) -> None:
        walkable = resolver.resolve_walkable_concept(concept_ref="harbour.Vessel")

        assert walkable.shape == ConceptShape.STRUCTURE
        walkable_field = walkable.get_field(name=field_name)
        assert walkable_field is not None
        assert walkable_field.value_kind == value_kind
        assert walkable_field.concept_ref == concept_ref
        assert walkable_field.is_list is is_list
        assert walkable_field.may_hold_nothing is may_hold_nothing

    def test_a_path_through_class_backed_concepts_derives(self, resolver: LibraryConceptWalkResolver) -> None:
        derivation = derive_binding(path="vessel.ports_of_call.name", root=BindingRoot(concept_ref="harbour.Vessel"), resolver=resolver)

        assert derivation.concept_ref == "native.Text"
        assert derivation.multiplicity is True

    def test_a_field_whose_class_maps_to_no_concept_is_refused(self, resolver: LibraryConceptWalkResolver) -> None:
        with pytest.raises(BindingPathUnresolvedError, match="_OrphanRecord"):
            derive_binding(path="vessel.stowaway", root=BindingRoot(concept_ref="harbour.Vessel"), resolver=resolver)

    def test_a_declared_structure_is_read_before_the_class(self, resolver: LibraryConceptWalkResolver) -> None:
        walkable = resolver.resolve_walkable_concept(concept_ref="harbour.Berth")

        assert walkable.shape == ConceptShape.STRUCTURE
        assert walkable.field_names == ["number"]

    def test_a_refinement_inherits_the_structure_it_refines(self, resolver: LibraryConceptWalkResolver) -> None:
        walkable = resolver.resolve_walkable_concept(concept_ref="harbour.GuestBerth")

        assert walkable.concept_ref == "harbour.GuestBerth"
        assert walkable.shape == ConceptShape.STRUCTURE
        assert walkable.field_names == ["number"]

    def test_a_native_is_read_off_its_pinned_definition(self, resolver: LibraryConceptWalkResolver) -> None:
        walkable = resolver.resolve_walkable_concept(concept_ref="native.Page")

        assert walkable.shape == ConceptShape.STRUCTURE
        page_view = walkable.get_field(name="page_view")
        assert page_view is not None
        assert page_view.concept_ref == "native.Image"

    @pytest.mark.parametrize(
        ("concept_ref", "shape_reason"),
        [
            pytest.param("harbour.Nowhere", "is not a concept of the library", id="unknown-concept"),
            pytest.param("harbour.Lost", "has a structure class that cannot be resolved", id="unresolvable-class"),
        ],
    )
    def test_a_concept_the_library_cannot_show_offers_nothing_to_walk(
        self, resolver: LibraryConceptWalkResolver, concept_ref: str, shape_reason: str
    ) -> None:
        walkable = resolver.resolve_walkable_concept(concept_ref=concept_ref)

        assert walkable.shape == ConceptShape.NO_STRUCTURE
        assert walkable.shape_reason == shape_reason
