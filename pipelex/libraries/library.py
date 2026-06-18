from pathlib import Path
from typing import TYPE_CHECKING

from kajson.class_registry import ClassRegistry
from pydantic import BaseModel, Field, PrivateAttr

from pipelex import log
from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.core.exceptions import PipesAndConceptValidationErrorData
from pipelex.core.pipes.exceptions import PipeValidationErrorType
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.libraries.concept.concept_library import ConceptLibrary
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.libraries.domain.domain_library import DomainLibrary
from pipelex.libraries.exceptions import LibraryError, LibraryLoadingError
from pipelex.libraries.pipe.exceptions import PipeLibraryError
from pipelex.libraries.pipe.pipe_library import PipeLibrary
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of

if TYPE_CHECKING:
    from pipelex.core.concepts.concept import Concept


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

    def validate_library(self) -> None:
        self.validate_domain_library_with_libraries()
        self.validate_concept_library_with_libraries()
        self.validate_pipe_library_with_libraries()

    def validate_pipe_library_with_libraries(self) -> None:
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
                        msg = f"Error validating pipe '{pipe.code}' dependency pipe '{sub_pipe_code}' because of: {pipe_error}"
                        # Carry a structured item so an unresolved dependency surfaces as a categorized
                        # `pipe_validation` item: `pipe_code` is the referencing controller and
                        # `missing_pipe_code` is the dependency that does not resolve, so a machine
                        # consumer can read both without parsing the message. LibraryLoadingError rides
                        # the existing `except LibraryError` forwarding in _translate_to_validate_bundle_error.
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
