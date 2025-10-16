from pathlib import Path
from typing import ClassVar

from typing_extensions import override

from pipelex import log
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.exceptions import (
    ConceptLibraryError,
    LibraryError,
    PipeLibraryError,
)
from pipelex.libraries.library import Library
from pipelex.libraries.library_ids import SpecialLibraryId
from pipelex.libraries.library_manager_abstract import LibraryManagerAbstract
from pipelex.libraries.library_utils import (
    get_pipelex_package_dir_for_imports,
    get_pipelex_plx_files_from_dirs,
    get_pipelex_plx_files_from_package,
)
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.registries.class_registry_utils import ClassRegistryUtils
from pipelex.system.registries.func_registry import func_registry
from pipelex.system.registries.func_registry_utils import FuncRegistryUtils
from pipelex.types import StrEnum


class LibraryComponent(StrEnum):
    CONCEPT = "concept"
    PIPE = "pipe"

    @property
    def error_class(self) -> type[LibraryError]:
        match self:
            case LibraryComponent.CONCEPT:
                return ConceptLibraryError
            case LibraryComponent.PIPE:
                return PipeLibraryError


class LibraryManager(LibraryManagerAbstract):
    allowed_root_attributes: ClassVar[list[str]] = [
        "domain",
        "description",
        "system_prompt",
        "system_prompt_jto_structure",
        "prompt_template_to_structure",
    ]

    def __init__(self):
        # UNTITLED library is the fallback library for all others
        self._libraries: dict[str, Library] = {SpecialLibraryId.UNTITLED: Library.make_empty()}

    ############################################################
    # Manager lifecycle
    ############################################################

    @override
    def setup(self) -> None:
        self._libraries.clear()
        self.create_library(library_id=SpecialLibraryId.UNTITLED)

    @override
    def teardown(self) -> None:
        for library in self._libraries.values():
            library.teardown()
        self._libraries.clear()

    @override
    def reset(self) -> None:
        self.teardown()
        self.setup()

    @override
    def create_library(self, library_id: str):
        if library_id in self._libraries:
            msg = f"Library '{library_id}' already exists"
            raise LibraryError(msg)
        self._libraries[library_id] = Library.make_empty()

    @override
    def open_library(self, library_id: str) -> None:
        """Open a new library with the given library_id.

        The new library will inherit native concepts and base pipes from the BASE library.
        """
        if library_id in self._libraries:
            msg = f"Library '{library_id}' already exists"
            raise LibraryError(msg)

        # Create a new library that inherits from UNTITLED
        base_library = Library.make_base()
        self.create_library(library_id=library_id)
        self.set_library(library_id=library_id, library=base_library)

    ############################################################
    # Public library accessors
    ############################################################

    @override
    def set_library(self, library_id: str, library: Library) -> None:
        if library_id not in self._libraries:
            msg = f"Library '{library_id}' does not exist"
            raise LibraryError(msg)
        self._libraries[library_id] = library

    @override
    def get_library(self, library_id: str | None = None) -> Library:
        """Get the Library object for a specific library_id."""
        if library_id is None:
            library_id = SpecialLibraryId.UNTITLED
        if library_id not in self._libraries:
            msg = f"Trying to get a library that does not exist: '{library_id}'"
            raise LibraryError(msg)
        return self._libraries[library_id]

    ############################################################
    # Private methods
    ############################################################

    @override
    def load_libraries(
        self,
        library_id: str | None = None,
        library_dirs: list[Path] | None = None,
        library_file_paths: list[Path] | None = None,
    ) -> None:
        if library_id is None:
            library_id = SpecialLibraryId.UNTITLED

        # Ensure libraries exist for this library_id
        if library_id not in self._libraries:
            msg = f"Trying to load a library that does not exist: '{library_id}'"
            raise LibraryError(msg)

        # Collect directories to scan (user project directories)
        user_dirs: set[Path] = set()
        if library_dirs:
            user_dirs.update(library_dirs)
        else:
            user_dirs.add(Path(config_manager.local_root_dir))

        # Get PLX file paths
        valid_plx_paths: list[Path]
        if library_file_paths:
            valid_plx_paths = library_file_paths
        else:
            # Get PLX files from user directories
            user_plx_paths: list[Path] = get_pipelex_plx_files_from_dirs(user_dirs)

            # Get PLX files from pipelex package
            pipelex_plx_paths: list[Path] = get_pipelex_plx_files_from_package()

            # Combine and deduplicate
            all_plx_paths = user_plx_paths + pipelex_plx_paths
            seen_absolute_paths: set[str] = set()
            valid_plx_paths = []
            for plx_path in all_plx_paths:
                try:
                    absolute_path = str(plx_path.resolve())
                except (OSError, RuntimeError):
                    # For paths that can't be resolved (e.g., in zipped packages), use string representation
                    absolute_path = str(plx_path)

                if absolute_path not in seen_absolute_paths:
                    valid_plx_paths.append(plx_path)
                    seen_absolute_paths.add(absolute_path)

        # Import modules and register in global registries
        # Import from user directories
        for library_dir in user_dirs:
            # Only import files that contain StructuredContent subclasses (uses AST pre-check)
            ClassRegistryUtils.import_modules_in_folder(
                folder_path=str(library_dir),
                base_class_names=[StructuredContent.__name__],
            )
            # Only import files that contain @pipe_func decorated functions (uses AST pre-check)
            FuncRegistryUtils.register_funcs_in_folder(
                folder_path=str(library_dir),
            )

        # Import from pipelex package
        # Always directly import critical builder modules first (works in all installation modes)
        log.verbose("About to import pipelex.builder modules for @pipe_func registration")
        self._import_pipelex_modules_directly()

        # Verify critical functions were registered
        # TODO: This should be a Unit test
        critical_functions = ["create_concept_spec", "assemble_pipelex_bundle_spec"]
        for func_name in critical_functions:
            if func_registry.has_function(func_name):
                log.verbose(f"✓ Function '{func_name}' successfully registered")
            else:
                log.error(f"✗ Function '{func_name}' NOT registered - this will cause errors!")

        # Then try filesystem-based scanning if package is accessible (for completeness)
        pipelex_pkg_dir = get_pipelex_package_dir_for_imports()
        if pipelex_pkg_dir:
            log.debug(f"Additionally scanning pipelex package filesystem: {pipelex_pkg_dir}")
            ClassRegistryUtils.import_modules_in_folder(
                folder_path=str(pipelex_pkg_dir),
                base_class_names=[StructuredContent.__name__],
            )
            FuncRegistryUtils.register_funcs_in_folder(
                folder_path=str(pipelex_pkg_dir),
            )

        # Auto-discover and register all StructuredContent classes from sys.modules
        num_registered = ClassRegistryUtils.auto_register_all_subclasses(
            base_class=StructuredContent,
        )
        log.debug(f"Auto-registered {num_registered} StructuredContent classes from loaded modules")

        # Delegate to the Library instance to load blueprints
        self.get_library(library_id=library_id).load_from_plx_files(plx_file_paths=valid_plx_paths)

    ############################################################
    # Private helper methods
    ############################################################

    def _import_pipelex_modules_directly(self) -> None:
        """Import pipelex modules to register @pipe_func decorated functions.

        This ensures critical pipelex functions are registered regardless of how pipelex
        is installed (wheel, source, relative path, etc.).
        """
        import pipelex.builder  # noqa: PLC0415 - intentional local import

        log.verbose("Registering @pipe_func functions from pipelex.builder")
        functions_count = FuncRegistryUtils.register_pipe_funcs_from_package("pipelex.builder", pipelex.builder)
        log.verbose(f"Registered {functions_count} @pipe_func functions from pipelex.builder")
