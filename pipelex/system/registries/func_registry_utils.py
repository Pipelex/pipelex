import importlib
import inspect
import pkgutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pipelex import log
from pipelex.config import get_config
from pipelex.system.registries.func_registry import func_registry, pipe_func
from pipelex.tools.misc.file_utils import find_files_in_dir
from pipelex.tools.typing.exceptions import ModuleFileError
from pipelex.tools.typing.module_inspector import import_module_from_file_if_has_decorated_functions


class FuncRegistryUtils:
    @classmethod
    def register_pipe_funcs_from_package(cls, package_name: str, *, package: Any) -> int:
        """Register all @pipe_func decorated functions from a package.

        Args:
            package_name: Full name of the package (e.g. "pipelex.builder")
            package: The imported package object

        Returns:
            Number of functions registered

        """
        functions_registered = 0

        if not hasattr(package, "__path__"):
            log.warning(f"Package {package_name} has no __path__ attribute, cannot walk modules")
            return 0

        log.verbose(f"Walking package {package_name} at {package.__path__}")

        for _importer, modname, _ispkg in pkgutil.walk_packages(
            path=package.__path__,
            prefix=f"{package_name}.",
            onerror=lambda _: None,
        ):
            # Import the module
            module = importlib.import_module(modname)
            log.verbose(f"Imported {modname}")

            # Find @pipe_func decorated functions in this module
            decorated_functions = cls._find_functions_in_module(module)

            for func in decorated_functions:
                func_name = cls._get_function_registration_name(func)

                # Check if the function is eligible for registration
                eligibility_error = func_registry.check_function_eligibility(func)

                if eligibility_error is None:
                    # Function is eligible - register it
                    func_registry.register_function(
                        func=func,
                        name=func_name,
                    )
                    functions_registered += 1
                    log.verbose(f"Registered @pipe_func: {func_name} from {modname}")
                else:
                    # Function has @pipe_func but is not eligible - track it for better error messages
                    func_registry.register_ineligible_function(
                        func=func,
                        reason=eligibility_error,
                        source_file=modname,
                    )
                    log.warning(f"Function '{func_name}' in '{modname}' has @pipe_func() decorator but is not eligible: {eligibility_error}")

        return functions_registered

    @classmethod
    def register_funcs_in_folder(
        cls,
        folder_path: Path,
        *,
        force_include_dirs: list[Path] | None = None,
        is_recursive: bool = True,
    ) -> None:
        """Discovers and attempts to register all functions in Python files within a folder.
        Only functions that meet the eligibility criteria will be registered:
        - Must be an async function
        - Exactly 1 parameter named "working_memory" with type WorkingMemory
        - Return type that is a subclass of StuffContent
        - Must be marked with the @pipe_func decorator

        Uses AST parsing to first check if files contain @pipe_func decorated functions
        before importing them. This avoids executing module-level code in files that
        don't contain the functions you're looking for.

        The function name is used as the registry key (or custom name if provided to decorator).

        Args:
            folder_path: Path to folder containing Python files
            is_recursive: Whether to search recursively in subdirectories
            force_include_dirs: List of directories to force include even if they are within excluded_dirs.

        """
        python_files = find_files_in_dir(
            dir_path=folder_path,
            pattern="*.py",
            is_recursive=is_recursive,
            excluded_dirs=list(get_config().pipelex.scan_config.excluded_dirs),
            force_include_dirs=[str(force_include_dir) for force_include_dir in force_include_dirs] if force_include_dirs is not None else None,
        )

        for python_file in python_files:
            cls._register_funcs_in_file(file_path=python_file)

    @classmethod
    def read_py_sources(
        cls,
        folder_path: Path,
        *,
        is_recursive: bool = True,
    ) -> dict[str, str]:
        """Capture the text of every Python file in a folder WITHOUT importing or executing any of it.

        This is the sandbox-hosted counterpart of ``register_funcs_in_folder``: instead of importing
        the customer's modules and registering ``@pipe_func`` functions in this process, it reads the
        raw source so the code can travel (on the crate) to an isolated sandbox where it is registered
        and run. It performs NO import — ``sys.modules`` is left untouched — which is what keeps the
        runner/worker from ever executing customer code.

        Discovery mirrors ``register_funcs_in_folder`` (same ``find_files_in_dir`` + ``excluded_dirs``)
        so the captured set matches what the local path would have imported. Both PipeFunc bodies and
        structure classes are captured, since the sandbox needs the customer's real classes too.

        Args:
            folder_path: Path to the folder containing Python files.
            is_recursive: Whether to search recursively in subdirectories.

        Returns:
            Mapping of POSIX relpath (relative to ``folder_path``) -> source text.
        """
        python_files = find_files_in_dir(
            dir_path=folder_path,
            pattern="*.py",
            is_recursive=is_recursive,
            excluded_dirs=list(get_config().pipelex.scan_config.excluded_dirs),
        )

        sources: dict[str, str] = {}
        for python_file in python_files:
            relative_path = python_file.relative_to(folder_path).as_posix()
            sources[relative_path] = python_file.read_text(encoding="utf-8")
        return sources

    @classmethod
    def _register_funcs_in_file(
        cls,
        file_path: Path,
    ) -> None:
        """Processes a Python file to find and register eligible @pipe_func decorated functions.

        Uses AST parsing to check if the file contains @pipe_func decorated functions before
        importing. Only functions marked with @pipe_func decorator are registered.

        If a function has @pipe_func decorator but is not eligible (e.g., missing return type),
        it is tracked as an ineligible function so that helpful error messages can be provided
        when the function is later looked up.

        Args:
            file_path: Path to the Python file

        """
        try:
            # Import the module only if it has @pipe_func decorated functions
            module = import_module_from_file_if_has_decorated_functions(
                file_path,
                decorator_names=[pipe_func.__name__],
            )
            # If no decorated functions found, module will be None
            if module is None:
                return

            # Find functions that match criteria (have @pipe_func decorator)
            decorated_functions = cls._find_functions_in_module(module)

            for func in decorated_functions:
                func_name = cls._get_function_registration_name(func)

                # Check if the function is eligible for registration
                eligibility_error = func_registry.check_function_eligibility(func)

                if eligibility_error is None:
                    # Function is eligible - register it
                    func_registry.register_function(
                        func=func,
                        name=func_name,
                    )
                else:
                    # Function has @pipe_func but is not eligible - track it for better error messages
                    func_registry.register_ineligible_function(
                        func=func,
                        reason=eligibility_error,
                        source_file=str(file_path),
                    )
                    log.warning(f"Function '{func_name}' in '{file_path}' has @pipe_func() decorator but is not eligible: {eligibility_error}")
        except ModuleFileError:
            # Expected: file validation issues (directories with .py extension, etc.)
            # log.verbose(f"Skipping file {file_path}: {e}")
            pass
        except ImportError as exc:
            # A module that fails to import (missing sibling module, circular import, bad relative
            # import) cannot contribute its @pipe_func functions — they never register. Surfacing this
            # is essential: the only downstream symptom is an opaque "Function '<name>' not found in
            # registry" raised much later by the PipeFunc validator, with the real ImportError (the
            # actual cause) otherwise swallowed here and invisible.
            log.warning(f"Could not import '{file_path}' while registering PipeFuncs; its functions are unavailable: {exc}")
        except SyntaxError as exc:
            # Potentially problematic: invalid Python syntax may indicate broken code
            log.warning(f"Syntax error in {file_path}: {exc}")

    @classmethod
    def _find_functions_in_module(
        cls,
        module: Any,
    ) -> list[Callable[..., Any]]:
        """Finds all @pipe_func decorated functions in a module.

        Only functions marked with @pipe_func decorator are included.
        Full eligibility (signature, return type) will be checked during registration.

        Args:
            module: The module to search for functions

        Returns:
            List of @pipe_func decorated functions found in the module

        """
        functions: list[Callable[..., Any]] = []
        module_name = module.__name__

        # Find all functions in the module (not imported ones)
        for _, obj in inspect.getmembers(module, inspect.isfunction):
            # Skip functions imported from other modules
            if obj.__module__ != module_name:
                continue

            # Only include functions marked with @pipe_func
            if not func_registry.is_marked_pipe_func(obj):
                continue

            # Add function - full eligibility will be checked by func_registry.register_function
            functions.append(obj)

        return functions

    @classmethod
    def _get_function_registration_name(cls, func: Callable[..., Any]) -> str:
        """Extract the registration name for a function.

        If the function has a custom name from the @pipe_func decorator, use that.
        Otherwise, use the function's __name__.

        Args:
            func: The function to get the registration name for

        Returns:
            The name to use when registering the function

        """
        custom_name = getattr(func, "_pipe_func_name", None)
        return custom_name if custom_name is not None else func.__name__
