import datetime
from typing import Any, cast

import pytest
from pydantic import Field
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.exceptions import ConceptStructureClassNotFoundError
from pipelex.core.stuffs.non_null_any import NonNullAny
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.libraries.concept.concept_library_abstract import ConceptLibraryAbstract
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.pipe_controllers.binding.binding_concept_resolvers import BlueprintConceptWalkResolver, LibraryConceptWalkResolver, library_concept_key
from pipelex.pipe_controllers.binding.binding_derivation import BindingRoot, BindingValueKind, ConceptShape, derive_binding
from pipelex.pipe_controllers.binding.exceptions import BindingPathUnresolvedError


class _HarbourRecord(StructuredContent):
    name: str


class _OrphanRecord(StructuredContent):
    label: str


class _CaptainRecord(StructuredContent):
    name: str


class _LogbookRecord(StructuredContent):
    captain: _CaptainRecord


def _default_escort() -> str:
    return "the harbour tug"


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
    berth_note: str | None
    pilot: str | None = "the harbour pilot"
    escort: str | None = Field(default_factory=_default_escort)
    draught: float = 4.5
    manifest: NonNullAny
    remarks: Any


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


def _make_concept_library(
    mocker: MockerFixture, *, concepts_by_key: dict[str, Concept], classes: dict[str, type[StuffContent]] | None = None
) -> ConceptLibraryAbstract:
    """A library holding each concept under its key, `alias->domain.Code` for a dependency's, looked up as the real one is."""
    concept_library: Any = mocker.MagicMock(spec=ConceptLibraryAbstract)
    known_classes = classes if classes is not None else _CLASSES

    def get_required_concept(concept_ref: str) -> Concept:
        if concept_ref in concepts_by_key:
            return concepts_by_key[concept_ref]
        if concept_ref == "native.Page":
            return _concept(code="Page", structure_class_name="PageContent", domain_code="native")
        msg = f"Concept '{concept_ref}' not found"
        raise ConceptLibraryError(msg)

    def list_concept_keys_for_ref(*, concept_ref: str) -> list[str]:
        direct_keys = [concept_ref] if concept_ref in concepts_by_key else []
        return direct_keys + sorted(key for key in concepts_by_key if key.endswith(f"->{concept_ref}"))

    def get_structure_class(*, concept: Concept) -> type[StuffContent]:
        if concept.structure_class_name not in known_classes:
            msg = f"No class '{concept.structure_class_name}'"
            raise ConceptStructureClassNotFoundError(msg)
        return known_classes[concept.structure_class_name]

    concept_library.get_required_concept.side_effect = get_required_concept
    concept_library.list_concept_keys_for_ref.side_effect = list_concept_keys_for_ref
    concept_library.get_structure_class.side_effect = get_structure_class
    concept_library.list_concepts.return_value = list(concepts_by_key.values())
    return cast("ConceptLibraryAbstract", concept_library)


@pytest.fixture
def resolver(mocker: MockerFixture) -> LibraryConceptWalkResolver:
    return LibraryConceptWalkResolver(concept_library=_make_concept_library(mocker, concepts_by_key=_CONCEPTS))


_HARBOUR_PACKAGE = "github.com/invented/harbour-lib/harbour"


def _structure_field(*, field_type: ConceptStructureBlueprintFieldType, **kwargs: Any) -> ConceptStructureBlueprint:
    return ConceptStructureBlueprint(description="A field", type=field_type, required=True, **kwargs)


# A host and a dependency package each declare `harbour.Manifest` and `harbour.Captain`, with different structures.
_HOST_MANIFEST = _concept(
    code="Manifest",
    structure_class_name="harbour__Manifest",
    declared_structure={
        "cargo_weight": _structure_field(field_type=ConceptStructureBlueprintFieldType.NUMBER),
        "captain": _structure_field(field_type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref="Captain"),
    },
)
_HOST_CAPTAIN = _concept(
    code="Captain",
    structure_class_name="_CaptainRecord",
    declared_structure={"licence": _structure_field(field_type=ConceptStructureBlueprintFieldType.TEXT)},
)
_PACKAGE_MANIFEST = _concept(
    code="Manifest",
    structure_class_name="harbour__Manifest",
    declared_structure={
        "tonnage": _structure_field(field_type=ConceptStructureBlueprintFieldType.NUMBER),
        "captain": _structure_field(field_type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref="harbour.Captain"),
        "crew": _structure_field(field_type=ConceptStructureBlueprintFieldType.LIST, item_type="concept", item_concept_ref="Captain"),
    },
)
_PACKAGE_CAPTAIN = _concept(
    code="Captain",
    structure_class_name="_CaptainRecord",
    declared_structure={"name": _structure_field(field_type=ConceptStructureBlueprintFieldType.TEXT)},
)
_PACKAGE_SEALED_MANIFEST = _concept(code="SealedManifest", structure_class_name="harbour__Manifest", refines="Manifest")
_PACKAGE_LOGBOOK = _concept(code="Logbook", structure_class_name="_LogbookRecord")
_HOST_LOGBOOK = _concept(code="Logbook", structure_class_name="_LogbookRecord")

_PACKAGE_CONCEPTS: dict[str, Concept] = {
    f"{_HARBOUR_PACKAGE}->harbour.Manifest": _PACKAGE_MANIFEST,
    f"{_HARBOUR_PACKAGE}->harbour.Captain": _PACKAGE_CAPTAIN,
    f"{_HARBOUR_PACKAGE}->harbour.SealedManifest": _PACKAGE_SEALED_MANIFEST,
    f"{_HARBOUR_PACKAGE}->harbour.Logbook": _PACKAGE_LOGBOOK,
}
_HOST_CONCEPTS: dict[str, Concept] = {
    "harbour.Manifest": _HOST_MANIFEST,
    "harbour.Captain": _HOST_CAPTAIN,
    "harbour.Logbook": _HOST_LOGBOOK,
}
_PACKAGE_CLASSES: dict[str, type[StuffContent]] = {"_CaptainRecord": _CaptainRecord, "_LogbookRecord": _LogbookRecord}


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
            pytest.param("berth_note", BindingValueKind.TEXT, None, False, True, id="required-but-nullable"),
            pytest.param("pilot", BindingValueKind.TEXT, None, False, True, id="nullable-with-a-default"),
            pytest.param("escort", BindingValueKind.TEXT, None, False, True, id="nullable-with-a-default-factory"),
            pytest.param("draught", BindingValueKind.NUMBER, None, False, False, id="not-nullable-with-a-default"),
            pytest.param("manifest", BindingValueKind.UNDERIVABLE, None, False, False, id="required-non-null-any"),
            pytest.param("remarks", BindingValueKind.UNDERIVABLE, None, False, True, id="required-but-any"),
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

    def test_a_required_field_that_admits_none_may_find_nothing(self, resolver: LibraryConceptWalkResolver) -> None:
        """A class field required but annotated `str | None` can hold `None`, so a single result read through it may be absent."""
        derivation = derive_binding(path="vessel.berth_note", root=BindingRoot(concept_ref="harbour.Vessel"), resolver=resolver)

        assert derivation.may_find_nothing is True
        assert derivation.first_optional_path == "vessel.berth_note"

    def test_both_spellings_of_a_description_only_concept_offer_nothing_to_walk(self, mocker: MockerFixture) -> None:
        """`Notice = "..."` and a `[concept.Bulletin]` table holding a description alone get one verdict, from both resolvers."""
        notice = ConceptFactory.make_from_blueprint(domain_code="harbour", concept_code="Notice", blueprint_or_string_description="A notice")
        bulletin = ConceptFactory.make_from_blueprint(
            domain_code="harbour", concept_code="Bulletin", blueprint_or_string_description=ConceptBlueprint(description="A bulletin")
        )
        assert notice.is_described_only
        assert bulletin.is_described_only
        assert bulletin.refines == "native.Text"
        library_resolver = LibraryConceptWalkResolver(
            concept_library=_make_concept_library(mocker, concepts_by_key={**_CONCEPTS, "harbour.Notice": notice, "harbour.Bulletin": bulletin})
        )
        blueprint_resolver = BlueprintConceptWalkResolver(
            concept_blueprints={"harbour.Notice": "A notice", "harbour.Bulletin": ConceptBlueprint(description="A bulletin")}
        )

        for walk_resolver in (library_resolver, blueprint_resolver):
            for root_name, concept_ref in (("notice", "harbour.Notice"), ("bulletin", "harbour.Bulletin")):
                walkable = walk_resolver.resolve_walkable_concept(concept_ref=concept_ref)
                assert walkable.shape == ConceptShape.NO_STRUCTURE
                assert walkable.shape_reason == "is declared with neither a structure nor refines"
                with pytest.raises(BindingPathUnresolvedError, match="is declared with neither a structure nor refines") as raised:
                    derive_binding(path=f"{root_name}.text", root=BindingRoot(concept_ref=concept_ref), resolver=walk_resolver)
                assert raised.value.failed_segment == "text"
                bare = derive_binding(path=root_name, root=BindingRoot(concept_ref=concept_ref), resolver=walk_resolver)
                assert bare.concept_ref == concept_ref

    @pytest.mark.parametrize(
        ("concept", "expected_key"),
        [
            pytest.param(_PACKAGE_MANIFEST, f"{_HARBOUR_PACKAGE}->harbour.Manifest", id="a-package-concept-by-identity"),
            pytest.param(_HOST_MANIFEST, "harbour.Manifest", id="a-host-concept-by-identity"),
            pytest.param(_PACKAGE_CAPTAIN.model_copy(), f"{_HARBOUR_PACKAGE}->harbour.Captain", id="a-copy-of-a-package-concept-by-equality"),
            pytest.param(_concept(code="Pier", structure_class_name="harbour__Pier"), "harbour.Pier", id="a-concept-the-library-lacks"),
        ],
    )
    def test_a_concept_is_keyed_where_the_library_holds_it(self, mocker: MockerFixture, concept: Concept, expected_key: str) -> None:
        concept_library = _make_concept_library(mocker, concepts_by_key={**_HOST_CONCEPTS, **_PACKAGE_CONCEPTS})

        assert library_concept_key(concept_library=concept_library, concept=concept) == expected_key

    @pytest.mark.parametrize(
        "host_concepts",
        [
            pytest.param({}, id="a-package-concept-alone"),
            pytest.param(_HOST_CONCEPTS, id="beside-host-concepts-of-the-same-spelling"),
        ],
    )
    def test_a_package_concept_is_walked_through_the_package_s_own_definitions(
        self, mocker: MockerFixture, host_concepts: dict[str, Concept]
    ) -> None:
        """Its fields, its list items, its refinements and its class-backed fields all name the package's concepts."""
        concept_library = _make_concept_library(mocker, concepts_by_key={**host_concepts, **_PACKAGE_CONCEPTS}, classes=_PACKAGE_CLASSES)
        package_resolver = LibraryConceptWalkResolver(concept_library=concept_library)
        root = BindingRoot(concept_ref=library_concept_key(concept_library=concept_library, concept=_PACKAGE_MANIFEST))

        assert root.concept_ref == f"{_HARBOUR_PACKAGE}->harbour.Manifest"
        assert derive_binding(path="manifest.tonnage", root=root, resolver=package_resolver).concept_ref == "native.Number"
        assert derive_binding(path="manifest.captain.name", root=root, resolver=package_resolver).concept_ref == "native.Text"
        assert derive_binding(path="manifest.captain", root=root, resolver=package_resolver).concept_ref == f"{_HARBOUR_PACKAGE}->harbour.Captain"
        crew = derive_binding(path="manifest.crew.name", root=root, resolver=package_resolver)
        assert crew.concept_ref == "native.Text"
        assert crew.multiplicity is True
        with pytest.raises(BindingPathUnresolvedError, match="has no field 'cargo_weight'"):
            derive_binding(path="manifest.cargo_weight", root=root, resolver=package_resolver)
        with pytest.raises(BindingPathUnresolvedError, match="has no field 'licence'"):
            derive_binding(path="manifest.captain.licence", root=root, resolver=package_resolver)

        sealed = BindingRoot(concept_ref=f"{_HARBOUR_PACKAGE}->harbour.SealedManifest")
        assert derive_binding(path="sealed.tonnage", root=sealed, resolver=package_resolver).concept_ref == "native.Number"

        logbook = package_resolver.resolve_walkable_concept(concept_ref=f"{_HARBOUR_PACKAGE}->harbour.Logbook")
        captain_field = logbook.get_field(name="captain")
        assert captain_field is not None
        assert captain_field.concept_ref == f"{_HARBOUR_PACKAGE}->harbour.Captain"

    def test_a_host_concept_is_walked_through_its_own_definitions_beside_a_package_namesake(self, mocker: MockerFixture) -> None:
        concept_library = _make_concept_library(mocker, concepts_by_key={**_HOST_CONCEPTS, **_PACKAGE_CONCEPTS}, classes=_PACKAGE_CLASSES)
        host_resolver = LibraryConceptWalkResolver(concept_library=concept_library)
        root = BindingRoot(concept_ref=library_concept_key(concept_library=concept_library, concept=_HOST_MANIFEST))

        assert root.concept_ref == "harbour.Manifest"
        assert derive_binding(path="manifest.captain.licence", root=root, resolver=host_resolver).concept_ref == "native.Text"
        assert derive_binding(path="manifest.captain", root=root, resolver=host_resolver).concept_ref == "harbour.Captain"
        with pytest.raises(BindingPathUnresolvedError, match="has no field 'tonnage'"):
            derive_binding(path="manifest.tonnage", root=root, resolver=host_resolver)
        logbook = host_resolver.resolve_walkable_concept(concept_ref="harbour.Logbook")
        captain_field = logbook.get_field(name="captain")
        assert captain_field is not None
        assert captain_field.concept_ref == "harbour.Captain"
