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
from pipelex.core.stuffs.stuff_content import StuffContent


class ConceptProviderAbstract(ABC):
    """Resolves concept references into concepts, and answers compatibility questions about them."""

    @abstractmethod
    def get_required_concept(self, concept_ref: str) -> Concept:
        """Resolve a fully-qualified concept ref, raising when it is not known."""

    @abstractmethod
    def get_native_concept(self, native_concept: NativeConceptCode) -> Concept:
        """Resolve one of the native concepts."""

    @abstractmethod
    def get_required_entry_concept(self, concept_ref_or_code: str, *, search_scope: str | None = None) -> Concept:
        """Resolve a concept string a *human* supplied — an input payload's `concept` field, a CLI argument.

        Entry-shaped lookup, not in-body reference resolution: natives resolve first, a
        fully-specified ref is a direct hit, and a bare code prefers `search_scope` (the entry
        pipe's own domain, `alias->domain` when the entry pipe came from a dependency package —
        in which case the rest of that package is searched next) before falling back to a
        crate-wide unique match. Every refusal — invalid string, no match, ambiguous bare code —
        raises the same exception class, so entry boundaries catch one thing.
        """

    @abstractmethod
    def is_compatible(self, *, tested_concept: Concept, wanted_concept: Concept, strict: bool = False) -> bool:
        """Whether `tested_concept` satisfies `wanted_concept` (refinement only when `strict`)."""

    @abstractmethod
    def get_structure_class(self, *, concept: Concept) -> type[StuffContent]:
        """Resolve a concept's declared `structure_class_name` into the class itself.

        A `Concept` carries the class *name* as a plain protocol string; turning that name into a
        type is a lookup against whichever class registry the provider is backed by, which is
        precisely the knowledge a wire model must not hold. Raises
        `ConceptStructureClassNotFoundError` when the name resolves to nothing, or to something that
        is not a `StuffContent` subclass.
        """
