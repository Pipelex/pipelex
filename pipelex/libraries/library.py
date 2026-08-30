from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from kajson.class_registry import ClassRegistry
from pydantic import BaseModel, Field, PrivateAttr

from pipelex import log
from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.core.exceptions import PipesAndConceptValidationErrorData
from pipelex.core.qualified_ref import QualifiedRef, QualifiedRefError
from pipelex.libraries.concept.concept_library import ConceptLibrary
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.libraries.domain.domain_library import DomainLibrary
from pipelex.libraries.exceptions import LibraryError, LibraryLoadingError
from pipelex.libraries.pipe.exceptions import PipeLibraryError, PipeNotFoundError
from pipelex.libraries.pipe.pipe_library import PipeLibrary
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
from pipelex.validation_error_types import PipeValidationErrorType

if TYPE_CHECKING:
    from pipelex.core.concepts.concept import Concept


def _describe_unresolved_pipe_dependency(
    *,
    referring_pipe_ref: str,
    missing_ref: str,
    candidates: dict[str, list[str]],
    cause: PipeLibraryError,
) -> str:
    """Explain an unresolved in-body pipe reference to the person who wrote it.

    The hard part is that the ref named here is not the ref they typed. They wrote a bare code; the
    compiler qualified it to their own domain. Without saying so, the message names a pipe that
    appears nowhere in their file and reads like a compiler bug.

    `candidates` comes from the failure-path-only scan in `_index_pipe_refs_by_bare_code`. A hit is a
    suggestion to a human, never a resolution — reaching a pipe in a domain nobody named is the
    behaviour this rule removed.
    """
    # Not every lookup failure is a miss. An ambiguous cross-package code raises here too, and for it
    # "does not exist" is false and the qualification story below never happened — so hand back the
    # real reason rather than a well-written wrong one.
    if not isinstance(cause, PipeNotFoundError):
        return f"Pipe '{referring_pipe_ref}' could not resolve its dependency '{missing_ref}': {cause}"

    lines = [f"Pipe '{referring_pipe_ref}' references '{missing_ref}', which does not exist."]

    # Everything below explains a rewrite, so it must only run on refs that could actually have been
    # rewritten. Three ways a ref reaches here without that being true:
    #   - a cross-package `alias->…` ref, which the pass leaves untouched;
    #   - a ref the author qualified themselves to ANOTHER domain — telling them their bare code was
    #     read as `beta.foo` when they typed `beta.foo` is a fiction, and the candidate scan holds
    #     host pipes that are the wrong thing to suggest for it;
    #   - a malformed ref, which does not parse at all. Parsing it to build a nicer message would
    #     replace a categorized validation error with a raw QualifiedRefError, turning bad user input
    #     into a crash on the way to reporting bad user input.
    if QualifiedRef.has_cross_package_prefix(missing_ref):
        return " ".join(lines)
    try:
        parsed = QualifiedRef.parse(missing_ref)
    except QualifiedRefError:
        return " ".join(lines)

    referring_domain = QualifiedRef.parse(referring_pipe_ref).domain_path
    if parsed.domain_path is not None and parsed.domain_path == referring_domain:
        # After qualification a bare ref and an explicitly-written same-domain ref are
        # indistinguishable, so the wording must not claim which one the author typed.
        local_code = parsed.local_code
        lines.append(
            f"A pipe reference resolves inside its own domain, so '{local_code}' is looked for in domain '{referring_domain}'. "
            "Referencing a pipe in another domain requires writing that domain out."
        )
        elsewhere = sorted(ref for ref in candidates.get(local_code, []) if ref != missing_ref)
        if elsewhere:
            suggestion = "' or '".join(elsewhere)
            lines.append(f"'{local_code}' is declared elsewhere in this library — did you mean '{suggestion}'?")

    return " ".join(lines)


class Library(BaseModel):
    """A Library bundles together domain, concept, and pipe libraries for a specific context.

    This represents a complete set of Pipelex definitions (domains, concepts, pipes)
    that can be loaded and used together, typically for a single pipeline run.

    Limitations: It lacks the Func Registry library and Class Registry library

    Each Library (except BASE) inherits native concepts and base pipes from the BASE library.
    """

    domain_library: DomainLibrary
    concept_library: ConceptLibrary
    pipe_library: PipeLibrary
    loaded_mthds_paths: list[Path] = Field(default_factory=empty_list_factory_of(Path))
    dependency_libraries: dict[str, "Library"] = Field(default_factory=dict)
    _class_registry: ClassRegistry | None = PrivateAttr(default=None)

    def get_class_registry(self) -> ClassRegistry | None:
        return self._class_registry

    def set_class_registry(self, class_registry: ClassRegistry) -> None:
        self._class_registry = class_registry

    def get_domain_library(self) -> DomainLibrary:
        return self.domain_library

    def get_concept_library(self) -> ConceptLibrary:
        return self.concept_library

    def get_pipe_library(self) -> PipeLibrary:
        return self.pipe_library

    def get_dependency_library(self, alias: str) -> "Library | None":
        """Get a child library for a dependency by alias.

        Args:
            alias: The dependency alias

        Returns:
            The child Library, or None if not found
        """
        return self.dependency_libraries.get(alias)

    def resolve_concept(self, concept_ref: str) -> "Concept | None":
        """Resolve a concept ref, routing cross-package refs through child libraries.

        For cross-package refs (containing '->'), splits into alias and remainder,
        then looks up the concept in the corresponding child library's concept_library.
        For local refs, looks up in the main concept_library.

        Args:
            concept_ref: A concept ref, possibly cross-package (e.g. "alias->domain.Code")

        Returns:
            The resolved Concept, or None if not found
        """
        if QualifiedRef.has_cross_package_prefix(concept_ref):
            alias, remainder = QualifiedRef.split_cross_package_ref(concept_ref)
            child_library = self.dependency_libraries.get(alias)
            if child_library is None:
                return None
            return child_library.concept_library.get_optional_concept(concept_ref=remainder)
        return self.concept_library.get_optional_concept(concept_ref=concept_ref)

    def teardown(self) -> None:
        # Tear down child libraries first
        for child_library in self.dependency_libraries.values():
            child_library.teardown()
        self.dependency_libraries = {}
        self.pipe_library.teardown()
        self.concept_library.teardown()
        self.domain_library.teardown()
        self.loaded_mthds_paths = []
        # Drop this library's dynamically generated structure classes with the library itself.
        # The registry object would be garbage anyway once the manager forgets the Library, but
        # a caller holding its own reference must not keep resolving a torn-down library's classes.
        if self._class_registry is not None:
            self._class_registry.teardown()
            self._class_registry = None

    def validate_library(self) -> None:
        self.validate_domain_library_with_libraries()
        self.validate_concept_library_with_libraries()
        self.validate_pipe_library_with_libraries()

    def validate_pipe_library_with_libraries(self) -> None:
        # Diagnostic index of bare code -> qualified refs, built at most once per validation run and
        # ONLY once something has already failed to resolve. This is the same crate-wide scan that was
        # deleted from `PipeLibrary.get_optional_pipe`; it lives on the FAILURE PATH ONLY and must stay
        # there. It suggests a spelling to a human — it never resolves a reference. Wiring it into a
        # lookup would restore the cross-domain fall-through and make `[exports]` unenforceable again.
        # Built once because the run this matters on is the mass-breakage one right after an upgrade,
        # where per-error scanning would go quadratic.
        bare_code_candidates: dict[str, list[str]] | None = None

        for pipe_key, pipe in self.pipe_library.root.items():
            # Determine if this pipe comes from a dependency (aliased key like "alias->pipe_code")
            dep_alias: str | None = None
            if QualifiedRef.has_cross_package_prefix(pipe_key):
                dep_alias, _remainder = QualifiedRef.split_cross_package_ref(pipe_key)

            # Validate concept dependencies exist
            # Note: This should NEVER fail as concepts are validated during pipe construction via get_required_concept()
            # TODO: Make this non mandatory in production, or a test
            for concept in pipe.concept_dependencies:
                try:
                    self.concept_library.is_concept_exists(concept_ref=concept.concept_ref)
                except ConceptLibraryError as concept_error:
                    msg = (
                        f"INTERNAL ERROR: Pipe '{pipe.code}' references concept '{concept.concept_ref}' "
                        f"which doesn't exist in the concept library. This should be impossible as concepts are "
                        f"validated during pipe construction (via get_required_concept() in pipe factories). "
                        f"This indicates a bug in the system. Original error: {concept_error}"
                    )
                    raise PipelexUnexpectedError(msg) from concept_error

            # Validate pipe dependencies exist for pipe controllers
            if isinstance(pipe, PipeController):
                for sub_pipe_code in pipe.pipe_dependencies():
                    # Cross-package refs that aren't loaded are validated at package level, not library level
                    if QualifiedRef.has_cross_package_prefix(sub_pipe_code) and self.pipe_library.get_optional_pipe(sub_pipe_code) is None:
                        continue
                    # For dependency pipes, look up bare sub-pipe codes in the child library
                    if dep_alias is not None and not QualifiedRef.has_cross_package_prefix(sub_pipe_code):
                        child_library = self.dependency_libraries.get(dep_alias)
                        if child_library is not None and child_library.pipe_library.get_optional_pipe(sub_pipe_code) is not None:
                            continue
                    try:
                        self.pipe_library.get_required_pipe(pipe_code=sub_pipe_code)
                    except PipeLibraryError as pipe_error:
                        if bare_code_candidates is None:
                            bare_code_candidates = self._index_pipe_refs_by_bare_code()
                        msg = _describe_unresolved_pipe_dependency(
                            referring_pipe_ref=pipe.pipe_ref,
                            missing_ref=sub_pipe_code,
                            candidates=bare_code_candidates,
                            cause=pipe_error,
                        )
                        # Carry a structured item so an unresolved dependency surfaces as a categorized
                        # `pipe_validation` item: `pipe_code` is the referencing controller and
                        # `missing_pipe_code` is the dependency that does not resolve, so a machine
                        # consumer can read both without parsing the message. LibraryLoadingError rides
                        # the existing `except LibraryError` forwarding in translate_to_validate_bundle_error.
                        dependency_error_data = PipesAndConceptValidationErrorData(
                            error_type=PipeValidationErrorType.UNRESOLVED_PIPE_DEPENDENCY,
                            domain_code=pipe.domain_code,
                            pipe_code=pipe.code,
                            missing_pipe_code=sub_pipe_code,
                            message=msg,
                            field_path=f"pipe.{pipe.code}",
                        )
                        raise LibraryLoadingError(message=msg, pipe_concept_validation_errors=[dependency_error_data]) from pipe_error

        for pipe in self.pipe_library.root.values():
            # Skip full validation for pipe controllers with unresolved cross-package dependencies
            if isinstance(pipe, PipeController) and self._has_unresolved_cross_package_deps(pipe):
                continue
            pipe.validate_with_libraries()

    def _index_pipe_refs_by_bare_code(self) -> dict[str, list[str]]:
        """Group every pipe ref in this library by its bare code, for failure-path diagnostics only.

        Aliased dependency entries are excluded: suggesting a pipe that only exists because some
        unrelated package happens to be installed is worse than suggesting nothing.
        """
        by_code: dict[str, list[str]] = defaultdict(list)
        for pipe_ref in self.pipe_library.root:
            if QualifiedRef.has_cross_package_prefix(pipe_ref):
                continue
            by_code[QualifiedRef.parse(pipe_ref).local_code].append(pipe_ref)
        return by_code

    def _has_unresolved_cross_package_deps(self, pipe: PipeController) -> bool:
        """Check if a pipe controller has cross-package dependencies that aren't loaded.

        A cross-package dep is only "unresolved" if the alias has no child library
        AND the pipe isn't found in the main pipe library.

        Args:
            pipe: The pipe controller to check

        Returns:
            True if the pipe has unresolved cross-package dependencies
        """
        for dep_code in pipe.pipe_dependencies():
            if QualifiedRef.has_cross_package_prefix(dep_code):
                # Check main pipe library first (aliased entries)
                if self.pipe_library.get_optional_pipe(dep_code) is not None:
                    continue
                # Check if the alias has a child library
                alias, _remainder = QualifiedRef.split_cross_package_ref(dep_code)
                if alias not in self.dependency_libraries:
                    return True
        return False

    def validate_concept_library_with_libraries(self) -> None:
        """Validate cross-package concept refines have their targets available.

        For each concept with a cross-package refines, verify the target exists
        in the corresponding child library via resolve_concept().
        """
        for concept in self.concept_library.root.values():
            if concept.refines and QualifiedRef.has_cross_package_prefix(concept.refines):
                resolved = self.resolve_concept(concept.refines)
                if resolved is None:
                    alias, remainder = QualifiedRef.split_cross_package_ref(concept.refines)
                    if alias in self.dependency_libraries:
                        msg = (
                            f"Concept '{concept.concept_ref}' refines cross-package concept '{concept.refines}' "
                            f"but '{remainder}' was not found in dependency '{alias}'"
                        )
                        raise LibraryError(msg)
                    log.verbose(
                        f"Concept '{concept.concept_ref}' refines cross-package concept '{concept.refines}' "
                        f"from unloaded dependency '{alias}', skipping validation"
                    )

    def validate_domain_library_with_libraries(self) -> None:
        pass
