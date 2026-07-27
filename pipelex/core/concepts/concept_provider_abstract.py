"""The read-side concept-resolution contract, owned by `core/` rather than by the library.

`core/` needs to *resolve* concepts — turn a ref, a code, or a native code into a `Concept`, and
ask whether two of them are compatible. It has no business *managing* a concept library (adding,
removing, listing, setup/teardown); that half is the loaded method's concern and stays in the
interpreter layer, on `ConceptLibraryAbstract`, which extends this.

Splitting the two is what lets `core/` state its dependency honestly: a core module declares "I
need something that can resolve concepts" as a parameter, instead of reaching for
`interpreter_hub.get_concept_library()` and dragging the whole interpreter into its import closure.
See ``docs/contribute/hub-layering.md``.
"""

from abc import ABC, abstractmethod

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.native.concept_native import NativeConceptCode


class ConceptProviderAbstract(ABC):
    """Resolves concept references into concepts, and answers compatibility questions about them."""

    @abstractmethod
    def get_required_concept(self, concept_ref: str) -> Concept:
        """Resolve a fully-qualified concept ref, raising when it is not known."""

    @abstractmethod
    def get_native_concept(self, native_concept: NativeConceptCode) -> Concept:
        """Resolve one of the native concepts."""

    @abstractmethod
    def get_required_concept_from_concept_ref_or_code(self, concept_ref_or_code: str, *, search_domain_codes: list[str] | None = None) -> Concept:
        """Resolve a ref *or* a bare code, optionally restricting the domains searched for a bare code."""

    @abstractmethod
    def is_compatible(self, *, tested_concept: Concept, wanted_concept: Concept, strict: bool = False) -> bool:
        """Whether `tested_concept` satisfies `wanted_concept` (refinement only when `strict`)."""
