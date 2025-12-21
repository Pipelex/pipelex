from pydantic import Field, RootModel, model_validator
from typing_extensions import override

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.exceptions import ConceptLibraryConceptNotFoundError, ConceptStringError
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.validation import is_concept_ref_valid, validate_concept_ref_or_code
from pipelex.core.domains.domain import SpecialDomain
from pipelex.libraries.concept.concept_library_abstract import ConceptLibraryAbstract
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.types import Self

ConceptLibraryRoot = dict[str, Concept]


class ConceptLibrary(RootModel[ConceptLibraryRoot], ConceptLibraryAbstract):
    root: ConceptLibraryRoot = Field(default_factory=dict)

    @model_validator(mode="after")
    def validation_static(self):
        for concept in self.root.values():
            if concept.refines and concept.refines not in self.root:
                msg = f"Concept '{concept.code}' refines '{concept.refines}' but no concept with the code '{concept.refines}' exists"
                raise ConceptLibraryError(msg)
        return self

    @override
    def setup(self):
        pass

    @override
    def teardown(self):
        self.root = {}

    @override
    def reset(self):
        self.teardown()
        self.setup()

    # TODO: Rethink the make_empty of libraries. It doesn't makes sense to call the setup inside the make_empty method.
    @classmethod
    def make_empty(cls) -> Self:
        library = cls(root={})
        library.setup()
        return library

    @classmethod
    def make_empty_with_native_concepts(cls) -> Self:
        library = cls(root={})
        library.setup()
        library.add_concepts(
            concepts=[ConceptFactory.make_native_concept(native_concept_code=native_concept) for native_concept in NativeConceptCode.values_list()]
        )
        return library

    @override
    def list_concepts(self) -> list[Concept]:
        return list(self.root.values())

    @override
    def list_concepts_by_domain(self, domain_code: str) -> list[Concept]:
        return [concept for key, concept in self.root.items() if key.startswith(f"{domain_code}.")]

    @override
    def add_new_concept(self, concept: Concept):
        if concept.concept_ref in self.root:
            msg = f"Concept '{concept.concept_ref}' already exists in the library"
            raise ConceptLibraryError(msg)
        self.root[concept.concept_ref] = concept

    @override
    def add_concepts(self, concepts: list[Concept]):
        for concept in concepts:
            self.add_new_concept(concept=concept)

    @override
    def remove_concepts_by_concept_refs(self, concept_refs: list[str]) -> None:
        for concept_ref in concept_refs:
            if concept_ref in self.root:
                del self.root[concept_ref]

    @override
    def is_compatible(self, tested_concept: Concept, wanted_concept: Concept, strict: bool = False) -> bool:
        return Concept.are_concept_compatible(concept_1=tested_concept, concept_2=wanted_concept, strict=strict)

    def get_optional_concept(self, concept_ref: str) -> Concept | None:
        return self.root.get(concept_ref)

    @override
    def get_required_concept(self, concept_ref: str) -> Concept:
        """`concept_ref` can have the domain or not. If it doesn't have the domain, it is assumed to be native.
        If it is not native and doesnt have a domain, it should raise an error
        """
        if not is_concept_ref_valid(concept_ref=concept_ref):
            msg = f"Concept string '{concept_ref}' is not a valid concept string"
            raise ConceptLibraryError(msg)

        the_concept = self.get_optional_concept(concept_ref=concept_ref)
        if not the_concept:
            msg = f"Concept '{concept_ref}' not found in the library"
            raise ConceptLibraryError(msg)
        return the_concept

    @override
    def get_native_concept(self, native_concept: NativeConceptCode) -> Concept:
        the_native_concept = self.get_optional_concept(f"{SpecialDomain.NATIVE}.{native_concept}")
        if not the_native_concept:
            msg = f"Native concept '{native_concept}' not found in the library"
            raise ConceptLibraryConceptNotFoundError(msg)
        return the_native_concept

    def get_native_concepts(self) -> list[Concept]:
        """Create all native concepts from the hardcoded data"""
        return [self.get_native_concept(native_concept=native_concept) for native_concept in NativeConceptCode.values_list()]

    @override
    def get_required_concept_from_concept_ref_or_code(self, concept_ref_or_code: str, search_domain_codes: list[str] | None = None) -> Concept:
        try:
            validate_concept_ref_or_code(concept_ref_or_code=concept_ref_or_code)
        except ConceptStringError as exc:
            msg = f"Could not validate concept string or code '{concept_ref_or_code}': {exc}"
            raise ConceptLibraryError(msg) from exc

        if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=concept_ref_or_code):
            native_concept_ref = NativeConceptCode.get_validated_native_concept_ref(concept_ref_or_code=concept_ref_or_code)
            return self.get_native_concept(native_concept=NativeConceptCode(native_concept_ref.split(".")[1]))
        elif "." in concept_ref_or_code:
            return self.get_required_concept(concept_ref=concept_ref_or_code)
        else:
            found_concepts: list[Concept] = []
            if search_domain_codes is None:
                for concept in self.root.values():
                    if concept_ref_or_code == concept.code:
                        found_concepts.append(concept)
                if len(found_concepts) == 0:
                    msg = f"Concept '{concept_ref_or_code}' not found in the library and no search domains were provided"
                    raise ConceptLibraryConceptNotFoundError(msg)
                if len(found_concepts) > 1:
                    msg = f"Multiple concepts found for '{concept_ref_or_code}': {found_concepts}. Please specify the domain."
                    raise ConceptLibraryConceptNotFoundError(msg)
                return found_concepts[0]
            else:
                for domain_code in search_domain_codes:
                    if found_concept := self.get_required_concept(
                        concept_ref=ConceptFactory.make_concept_ref_with_domain(domain_code=domain_code, concept_code=concept_ref_or_code),
                    ):
                        found_concepts.append(found_concept)
                if len(found_concepts) == 0:
                    msg = f"Concept '{concept_ref_or_code}' not found in the library and no search domains were provided"
                    raise ConceptLibraryConceptNotFoundError(msg)
                if len(found_concepts) > 1:
                    msg = f"Multiple concepts found for '{concept_ref_or_code}': {found_concepts}. Please specify the domain."
                    raise ConceptLibraryConceptNotFoundError(msg)
                return found_concepts[0]

    def is_concept_exists(self, concept_ref: str) -> bool:
        return concept_ref in self.root
