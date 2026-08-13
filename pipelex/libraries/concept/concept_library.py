from typing import Any, Callable, Self, cast

from kajson.exceptions import ClassRegistryInheritanceError, ClassRegistryNotFoundError
from pydantic import Field, RootModel, model_validator
from typing_extensions import override

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.exceptions import ConceptLibraryConceptNotFoundError, ConceptStringError, ConceptStructureClassNotFoundError
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.validation import is_concept_ref_valid, validate_concept_ref_or_code
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.libraries.concept.concept_library_abstract import ConceptLibraryAbstract
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.runtime_hub import get_class_registry
from pipelex.tools.typing.class_utils import are_structure_classes_compatible

ConceptLibraryRoot = dict[str, Concept]


class ConceptLibrary(RootModel[ConceptLibraryRoot], ConceptLibraryAbstract):
    root: ConceptLibraryRoot = Field(default_factory=dict)

    @override
    def model_post_init(self, _context: Any) -> None:
        self._concept_resolver: Callable[[str], Concept | None] | None = None

    def set_concept_resolver(self, resolver: Callable[[str], Concept | None]) -> None:
        """Set a resolver callback for cross-package concept lookups.

        Args:
            resolver: A callable that takes a concept ref and returns the Concept or None
        """
        self._concept_resolver = resolver

    @model_validator(mode="after")
    def validation_static(self):
        for concept in self.root.values():
            if concept.refines and not QualifiedRef.has_cross_package_prefix(concept.refines) and concept.refines not in self.root:
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
    def is_compatible(self, *, tested_concept: Concept, wanted_concept: Concept, strict: bool = False) -> bool:
        """Compose the two compatibility tiers, in the one place that owns resolution.

        The declaration tier decides on its own whenever it can — and when it does, no class is ever
        looked up, so concepts whose structure classes were never materialized still get an answer.
        Only when the declarations are inconclusive does the class tier run, and that needs both
        classes: a name that does not resolve makes the question unanswerable, so it raises rather
        than returning the `False` that would read as "incompatible".
        """
        if Concept.are_compatible_by_declaration(
            concept_1=tested_concept,
            concept_2=wanted_concept,
            concept_resolver=self._concept_resolver,
        ):
            return True

        if not (tested_concept.declares_a_structure_class and wanted_concept.declares_a_structure_class):
            # `native.Anything` has no structure class, so there is no structural comparison left to
            # make: the declaration tier's silence is the whole answer.
            return False

        return are_structure_classes_compatible(
            class_1=self.get_structure_class(concept=tested_concept),
            class_2=self.get_structure_class(concept=wanted_concept),
            strict=strict,
        )

    @override
    def get_structure_class(self, *, concept: Concept) -> type[StuffContent]:
        try:
            structure_class = get_class_registry().get_required_subclass(name=concept.structure_class_name, base_class=StuffContent)
        except (ClassRegistryNotFoundError, ClassRegistryInheritanceError) as exc:
            msg = (
                f"Concept '{concept.concept_ref}' declares structure class '{concept.structure_class_name}', "
                f"which is not a registered subclass of StuffContent: {exc}"
            )
            raise ConceptStructureClassNotFoundError(msg) from exc
        return cast("type[StuffContent]", structure_class)

    def get_optional_concept(self, concept_ref: str) -> Concept | None:
        return self.root.get(concept_ref)

    @override
    def get_required_concept(self, concept_ref: str) -> Concept:
        """`concept_ref` can have the domain or not. If it doesn't have the domain, it is assumed to be native.
        If it is not native and doesnt have a domain, it should raise an error.
        Cross-package refs (alias->domain.Code) are looked up directly by key.
        """
        # Cross-package refs bypass format validation (direct dict lookup)
        if QualifiedRef.has_cross_package_prefix(concept_ref):
            the_concept = self.root.get(concept_ref)
            if not the_concept:
                alias, remainder = QualifiedRef.split_cross_package_ref(concept_ref)
                msg = f"Cross-package concept '{remainder}' from dependency '{alias}' not found in the library. Is the dependency loaded?"
                raise ConceptLibraryError(msg)
            return the_concept

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

    def get_optional_entry_concept(self, concept_ref_or_code: str, *, search_scope: str | None = None) -> Concept | None:
        """Resolve a concept string a **human** supplied — an input payload's `concept` field, a CLI argument.

        Entry-shaped lookup, the concept twin of `PipeLibrary.get_optional_entry_pipe` — kept a
        deliberate near-copy rather than a shared helper (see
        wip/pipe-refs/entry-affordance-share-vs-duplicate.md). Natives resolve first, per the
        standard's own step 1. A fully-specified ref (`domain.Concept`, `alias->domain.Concept`)
        is a direct hit or a miss. A bare code prefers `search_scope` — the entry pipe's own
        domain, carried as `alias->domain` when the entry pipe came from a dependency package —
        then, under an aliased scope, the rest of that dependency package (which may span several
        domains, all keyed under its one alias), then a crate-wide unique match. Dotted refs obey
        the same precedence: under an aliased scope the dependency's own `domain.Concept` wins
        over a host concept spelled identically. An ambiguous bare code raises rather than
        picking a winner.

        Aliased dependency entries are excluded from the crate-wide search: installing an
        unrelated package must not make a host concept's bare code ambiguous. They stay reachable
        through `search_scope` (the dependency the entry pipe belongs to) or an explicit
        `alias->…` ref.

        Raises:
            ConceptLibraryConceptNotFoundError: the string is not a valid concept ref or code,
                or a bare code matches concepts in several domains. One class for every refusal,
                so entry boundaries catch a single exception.
        """
        try:
            validate_concept_ref_or_code(concept_ref_or_code=concept_ref_or_code)
        except ConceptStringError as exc:
            msg = f"Could not validate concept string or code '{concept_ref_or_code}': {exc}"
            raise ConceptLibraryConceptNotFoundError(msg) from exc

        # Aliased ref: resolve within that package only. `alias->domain.Concept` is a direct hit;
        # `alias->Concept` searches the package the way a bare code searches the host crate.
        if QualifiedRef.has_cross_package_prefix(concept_ref_or_code):
            the_concept = self.root.get(concept_ref_or_code)
            if the_concept is not None:
                return the_concept
            ref_alias, remainder = QualifiedRef.split_cross_package_ref(concept_ref_or_code)
            if "." not in remainder:
                return self._search_dependency_package(alias=ref_alias, concept_code=remainder)
            return None

        if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=concept_ref_or_code):
            native_concept_ref = NativeConceptCode.get_validated_native_concept_ref(concept_ref_or_code=concept_ref_or_code)
            return self.get_native_concept(native_concept=NativeConceptCode(native_concept_ref.split(".")[1]))

        scope_alias: str | None = None
        scope_domain: str | None = None
        if search_scope:
            if QualifiedRef.has_cross_package_prefix(search_scope):
                scope_alias, scope_domain = QualifiedRef.split_cross_package_ref(search_scope)
            else:
                scope_domain = search_scope

        if "." in concept_ref_or_code:
            if scope_alias:
                # Scope wins for dotted refs too: the entry pipe came from a dependency package
                # whose concepts are keyed under the alias, so a ref naming one of that package's
                # own domains reaches the package's concept even when the host declares the same
                # `domain.Concept` spelling — same precedence as the bare-code arm below.
                the_concept = self.root.get(f"{scope_alias}->{concept_ref_or_code}")
                if the_concept is not None:
                    return the_concept
            return self.root.get(concept_ref_or_code)

        # Bare code: the entry pipe's own scope wins before any search.
        if scope_domain:
            scoped_ref = ConceptFactory.make_concept_ref_with_domain(domain_code=scope_domain, concept_code=concept_ref_or_code)
            if scope_alias:
                scoped_ref = f"{scope_alias}->{scoped_ref}"
            the_concept = self.root.get(scoped_ref)
            if the_concept is not None:
                return the_concept

        # A dependency entry pipe then searches the rest of its own package: a multi-domain
        # dependency keys every concept under its one alias, so the bare code may be declared in
        # a sibling domain of the same package.
        if scope_alias:
            the_concept = self._search_dependency_package(alias=scope_alias, concept_code=concept_ref_or_code)
            if the_concept is not None:
                return the_concept

        matches = [
            concept for key, concept in self.root.items() if not QualifiedRef.has_cross_package_prefix(key) and concept.code == concept_ref_or_code
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            candidates = sorted(match.concept_ref for match in matches)
            msg = f"Concept code '{concept_ref_or_code}' is ambiguous — it is declared by {candidates}. Name one of them explicitly."
            raise ConceptLibraryConceptNotFoundError(msg)
        return None

    @override
    def get_required_entry_concept(self, concept_ref_or_code: str, *, search_scope: str | None = None) -> Concept:
        the_concept = self.get_optional_entry_concept(concept_ref_or_code=concept_ref_or_code, search_scope=search_scope)
        if not the_concept:
            msg = f"Concept '{concept_ref_or_code}' not found in the library. Check for typos and make sure its bundle is loaded."
            raise ConceptLibraryConceptNotFoundError(msg)
        return the_concept

    def _search_dependency_package(self, *, alias: str, concept_code: str) -> Concept | None:
        """Search one dependency package's aliased entries for a bare concept code.

        The package-scoped twin of the crate-wide bare-code search: a dependency may span several
        domains, all keyed under its one alias. Alias-scoped by construction, so it can never
        reach a host concept.

        Raises:
            ConceptLibraryConceptNotFoundError: the code is declared in several of the package's domains.
        """
        prefix = f"{alias}->"
        matches = [concept for key, concept in self.root.items() if key.startswith(prefix) and concept.code == concept_code]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            candidates = sorted(f"{prefix}{match.concept_ref}" for match in matches)
            msg = (
                f"Concept code '{concept_code}' is ambiguous within dependency '{alias}' — it is declared by {candidates}. "
                "Name one of them explicitly."
            )
            raise ConceptLibraryConceptNotFoundError(msg)
        return None

    def add_dependency_concept(self, *, alias: str, concept: Concept) -> None:
        """Add a concept from a dependency package with an aliased key.

        Args:
            alias: The dependency alias
            concept: The concept to add
        """
        key = f"{alias}->{concept.concept_ref}"
        if key in self.root:
            msg = f"Dependency concept '{key}' already exists in the library"
            raise ConceptLibraryError(msg)
        self.root[key] = concept

    def is_concept_exists(self, concept_ref: str) -> bool:
        return concept_ref in self.root
