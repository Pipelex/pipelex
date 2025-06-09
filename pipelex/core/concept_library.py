from typing import Dict, List, Optional

from pydantic import Field, RootModel
from typing_extensions import override

from pipelex import log
from pipelex.core.concept import Concept
from pipelex.core.concept_factory import ConceptFactory
from pipelex.core.concept_native import NativeConcept
from pipelex.core.concept_provider_abstract import ConceptProviderAbstract
from pipelex.exceptions import ConceptLibraryConceptNotFoundError, ConceptLibraryError

ConceptLibraryRoot = Dict[str, Concept]


class ConceptLibrary(RootModel[ConceptLibraryRoot], ConceptProviderAbstract):
    root: ConceptLibraryRoot = Field(default_factory=dict)

    def validate_with_libraries(self):
        for concept in self.root.values():
            for domain_concept_code in concept.refines:
                if "." in domain_concept_code:
                    domain, concept_code = Concept.extract_domain_and_concept_from_str(concept_str=domain_concept_code)

                    found_concept = self.root.get(f"{domain}.{concept_code}", None)
                    if not found_concept:
                        raise ConceptLibraryError(
                            f"Concept '{concept.code}' refines '{domain_concept_code}' but no concept "
                            f"with the code '{concept_code}' and domain '{domain}' exists"
                        )
                else:
                    current_domain = concept.domain
                    found_concept = self.root.get(f"{current_domain}.{domain_concept_code}", None)
                    if not found_concept:
                        raise ConceptLibraryError(
                            f"Concept '{concept.code}' refines '{domain_concept_code}' but no concept "
                            f"with the code '{domain_concept_code}' and domain '{current_domain}' exists"
                        )
                    if found_concept.domain != current_domain:
                        raise ConceptLibraryError(
                            f"Concept '{concept.code}' refines '{domain_concept_code}' but the concept "
                            f"exists in domain '{found_concept.domain}' and not in the same domain '{current_domain}'"
                        )

                self.get_required_concept(concept_code=domain_concept_code)

    def reset(self):
        self.root = {}

    @override
    def is_concept_implicit(self, concept_code: str) -> bool:
        concept_names = self._list_concept_names()
        is_implicit = concept_code not in concept_names
        if is_implicit:
            log.debug(f"Concept '{concept_code}' is implicit")
        return is_implicit

    @override
    def list_concepts(self) -> List[Concept]:
        return list(self.root.values())

    def _list_concept_names(self) -> List[str]:
        return [Concept.extract_domain_and_concept_from_str(c.code)[1] for c in self.list_concepts()]

    @override
    def list_concepts_by_domain(self, domain: str) -> List[Concept]:
        return [concept for key, concept in self.root.items() if key.startswith(f"{domain}.")]

    def add_new_concept(self, concept: Concept):
        name = concept.code
        if name in self.root:
            raise ConceptLibraryError(f"Concept '{name}' already exists in the library")
        self.root[name] = concept

    def add_concepts(self, concepts: List[Concept]):
        for concept in concepts:
            self.add_new_concept(concept=concept)

    @override
    def is_compatible(self, tested_concept: Concept, wanted_concept: Concept) -> bool:
        if tested_concept.code == wanted_concept.code:
            return True
        for inherited_concept_code in tested_concept.refines:
            inherited_concept = self.get_required_concept(concept_code=inherited_concept_code)
            if self.is_compatible(inherited_concept, wanted_concept):
                return True
        return False

    @override
    def is_compatible_by_concept_code(self, tested_concept_code: str, wanted_concept_code: str) -> bool:
        if wanted_concept_code == NativeConcept.ANYTHING.code:
            return True
        tested_concept = self.get_required_concept(concept_code=tested_concept_code)
        wanted_concept = self.get_required_concept(concept_code=wanted_concept_code)
        if tested_concept.code == wanted_concept.code:
            return True
        for inherited_concept_code in tested_concept.refines:
            if self.is_compatible_by_concept_code(inherited_concept_code, wanted_concept_code):
                return True
        return False

    @override
    def get_concept(self, concept_code: str) -> Optional[Concept]:
        return self.root.get(concept_code, None)

    @override
    def get_required_concept(self, concept_code: str) -> Concept:
        the_concept = self.get_concept(concept_code=concept_code)
        if not the_concept:
            if self.is_concept_implicit(concept_code=concept_code):
                # The implicit concept is obviously coming with a domain (the one it is used in)
                # TODO: replace this with a concept factory method make_implicit_concept
                return ConceptFactory.make_concept_from_definition(
                    domain_code="implicit",
                    code=Concept.extract_domain_and_concept_from_str(concept_str=concept_code)[1],
                    definition=concept_code,
                )
            else:
                raise ConceptLibraryConceptNotFoundError(f"Concept code was not found and is not implicit: '{concept_code}'")
        return the_concept

    @override
    def get_concepts_dict(self) -> Dict[str, Concept]:
        return self.root

    @override
    def teardown(self) -> None:
        self.root = {}
