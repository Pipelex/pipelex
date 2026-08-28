import inspect
import logging
from collections.abc import Callable
from typing import Any, TypeVar, cast, get_origin, get_type_hints

from pydantic import Field, PrivateAttr, RootModel
from typing_extensions import override

from pipelex.system.registries.exceptions import FuncRegistryError
from pipelex.urls import URLs

FUNC_REGISTRY_LOGGER_CHANNEL_NAME = "func_registry"

# Type variable for generic function types
T = TypeVar("T")
FuncRegistryDict = dict[str, Callable[..., Any]]

# Attribute name used by the decorator to mark functions for registration
PIPE_FUNC_MARKER = "_is_pipe_func"


def _describe_function_origin(*, func: Callable[..., Any]) -> str:
    """Renders where a registered function came from, for collision diagnostics.

    Modules imported by file path get a name mangled from their absolute path, so the module name
    alone is enough to point the author at the offending file.
    """
    module_name = getattr(func, "__module__", None) or "<unknown module>"
    qualified_name = getattr(func, "__qualname__", None) or getattr(func, "__name__", "<unknown function>")
    return f"'{qualified_name}' from module '{module_name}'"


def pipe_func(name: str | None = None) -> Callable[[T], T]:
    """Decorator to mark a function for automatic registration in the func_registry.

    This decorator marks functions to be discovered and registered for use in PipeFunc operators.
    Functions marked with this decorator must follow the PipeFunc signature:
    - Accept exactly one parameter named "working_memory" of type WorkingMemory
    - Return a StuffContent or subclass

    Args:
        name: Optional custom name for registration. If not provided, uses function's __name__

    Returns:
        The decorated function unchanged, but marked for registration

    Example:
        @pipe_func()
        async def my_custom_function(working_memory: WorkingMemory) -> TextContent:
            result = working_memory.get_stuff("input")
            return TextContent(text=f"Processed: {result}")

        @pipe_func(name="custom_name")
        async def another_function(working_memory: WorkingMemory) -> MyContent:
            return MyContent(data="example")

    """

    def decorator(func: T) -> T:
        # Mark the function with the attribute
        setattr(func, PIPE_FUNC_MARKER, True)
        # Store custom name if provided
        if name is not None:
            func._pipe_func_name = name  # type: ignore[attr-defined] # ruff: ignore[private-member-access]
        return func

    return decorator


class IneligibleFunctionInfo:
    """Information about a function that has @pipe_func decorator but failed eligibility checks."""

    def __init__(self, func_name: str, reason: str, source_file: str | None = None):
        self.func_name = func_name
        self.reason = reason
        self.source_file = source_file

    @override
    def __str__(self) -> str:
        if self.source_file:
            return f"Function '{self.func_name}' in '{self.source_file}': {self.reason}"
        return f"Function '{self.func_name}': {self.reason}"


# Type for tracking ineligible decorated functions
IneligibleFuncsDict = dict[str, IneligibleFunctionInfo]


def _make_ineligible_funcs_dict() -> IneligibleFuncsDict:
    """Factory function for creating an empty ineligible functions dict with proper typing."""
    return {}


class FuncRegistry(RootModel[FuncRegistryDict]):
    root: FuncRegistryDict = Field(default_factory=dict)
    _logger: logging.Logger = PrivateAttr(logging.getLogger(FUNC_REGISTRY_LOGGER_CHANNEL_NAME))
    _ineligible_decorated_funcs: IneligibleFuncsDict = PrivateAttr(default_factory=_make_ineligible_funcs_dict)

    def log(self, message: str) -> None:
        self._logger.debug(message)

    def set_logger(self, logger: logging.Logger) -> None:
        self._logger = logger

    def teardown(self) -> None:
        """Resets the registry to an empty state."""
        self.root.clear()
        self._ineligible_decorated_funcs.clear()

    def register_function(
        self,
        func: Callable[..., Any],
        *,
        name: str | None = None,
    ) -> None:
        """Registers a function in the registry with a name if it meets eligibility criteria.

        Raises:
            FuncRegistryError: If a *different* function is already registered under the same name.
                Registering the same function object again is a no-op, so a folder scanned twice
                (the same module object is reused from ``sys.modules``) stays idempotent.

        """
        if not self.is_eligible_function(func):
            return

        key = name or func.__name__
        already_registered = self.root.get(key)
        if already_registered is not None:
            if already_registered is func:
                self.log(f"Function '{key}' is already registered in registry with the same function object")
                return
            msg = (
                f"Function name '{key}' is already registered by a different function: "
                f"{_describe_function_origin(func=already_registered)} would be replaced by {_describe_function_origin(func=func)}. "
                f"PipeFunc names share a single flat, process-wide name space, so which one wins would depend on "
                f'scan order. Give one of them a distinct name with @pipe_func(name="..."). '
                f"See: {URLs.pipe_func_docs}"
            )
            raise FuncRegistryError(msg)

        self.log(f"Registered new single function '{key}' in registry")
        self.root[key] = func

    def unregister_function(self, func: Callable[..., Any]) -> None:
        """Unregisters a function from the registry."""
        key = func.__name__
        if key not in self.root:
            msg = f"Function '{key}' not found in registry"
            raise FuncRegistryError(msg)
        del self.root[key]
        self.log(f"Unregistered single function '{key}' from registry")

    def unregister_function_by_name(self, name: str) -> None:
        """Unregisters a function from the registry by its name."""
        if name not in self.root:
            msg = f"Function '{name}' not found in registry"
            raise FuncRegistryError(msg)
        del self.root[name]

    def register_functions_dict(self, functions: dict[str, Callable[..., Any]]) -> None:
        """Registers multiple functions in the registry with names if they meet eligibility criteria."""
        for name, func in functions.items():
            self.register_function(func=func, name=name)

    def register_functions(self, functions: list[Callable[..., Any]]) -> None:
        """Registers multiple functions in the registry with names if they meet eligibility criteria."""
        for func in functions:
            self.register_function(func=func)

    def get_function(self, name: str) -> Callable[..., Any] | None:
        """Retrieves a function from the registry by its name. Returns None if not found."""
        return self.root.get(name)

    def get_required_function(self, name: str) -> Callable[..., Any]:
        """Retrieves a function from the registry by its name. Raises an error if not found."""
        if name not in self.root:
            # Check if this function was found but is ineligible
            ineligible_info = self._ineligible_decorated_funcs.get(name)
            if ineligible_info:
                msg = (
                    f"Function '{name}' has @pipe_func() decorator but is not eligible for registration: "
                    f"{ineligible_info.reason}. "
                    f"See: {URLs.pipe_func_docs}"
                )
            else:
                msg = (
                    f"Function '{name}' not found in registry. "
                    f"Since v0.12.0, custom functions require the @pipe_func() decorator for auto-discovery. "
                    f"Add @pipe_func() above your function definition. "
                    f"See: {URLs.pipe_func_docs}"
                )
            raise FuncRegistryError(msg)
        return self.root[name]

    def get_required_function_with_signature(self, name: str) -> Callable[..., object]:
        """Retrieves a function from the registry by its name and verifies it matches the expected signature.
        Raises an error if not found or if signature doesn't match.
        """
        if name not in self.root:
            msg = f"Function '{name}' not found in registry"
            raise FuncRegistryError(msg)

        func = self.root[name]
        # Note: This is a basic signature check. For more thorough type checking,
        # you might want to use typing.get_type_hints() or a more sophisticated type checker
        if not callable(func):
            msg = f"'{name}' is not a callable function"
            raise FuncRegistryError(msg)
        return func

    def has_function(self, name: str) -> bool:
        """Checks if a function is in the registry by its name."""
        return name in self.root

    def is_marked_pipe_func(self, func: Any) -> bool:
        """Checks if a function is marked with the @pipe_func decorator.

        Args:
            func: The function to check

        Returns:
            True if the function has the pipe_func marker attribute

        """
        return hasattr(func, PIPE_FUNC_MARKER) and getattr(func, PIPE_FUNC_MARKER) is True

    # TODO: refactor this into a subclass of FuncRegistry dedicated to pipe funcs, avoid the circular import issue, avoid the code-smell
    def is_eligible_function(self, func: Any, *, require_decorator: bool = False) -> bool:
        """Checks if a function matches the criteria for PipeFunc registration:
        - Must be callable
        - Exactly 1 parameter named "working_memory" with type WorkingMemory
        - Return type that is a subclass of StuffContent
        - Optionally must be marked with @pipe_func decorator if require_decorator=True

        Args:
            func: The function to check
            require_decorator: If True, only functions marked with @pipe_func are eligible

        Returns:
            True if the function meets all eligibility criteria

        """
        if not callable(func):
            return False

        # If decorator is required, check for it first (fast check)
        if require_decorator and not self.is_marked_pipe_func(func):
            return False

        the_function = cast("Callable[..., Any]", func)

        # Import here to avoid circular imports
        # TODO: code-smell
        from pipelex.core.memory.working_memory import WorkingMemory  # ruff: ignore[import-outside-top-level]
        from pipelex.core.stuffs.stuff_content import StuffContent  # ruff: ignore[import-outside-top-level]

        # Get function signature
        sig = inspect.signature(the_function)
        params = list(sig.parameters.values())

        # Check parameter count and name
        if len(params) != 1:
            return False

        param = params[0]
        if param.name != "working_memory":
            return False

        # Get type hints
        type_hints = get_type_hints(the_function)

        # Check parameter type
        if "working_memory" not in type_hints:
            return False

        param_type = type_hints["working_memory"]
        if param_type != WorkingMemory:
            return False

        # Check return type
        if "return" not in type_hints:
            return False

        return_type = type_hints["return"]

        # Check if return type is a subclass of StuffContent
        try:
            if inspect.isclass(return_type) and issubclass(return_type, StuffContent):
                return True
            # Handle generic types like ListContent[SomeType]
            origin = get_origin(return_type)
            if inspect.isclass(origin) and issubclass(origin, StuffContent):
                return True
        except TypeError:
            # Handle cases where issubclass fails on generic types
            pass

        return False

    def check_function_eligibility(self, func: Any) -> str | None:
        """Check if a function is eligible for PipeFunc registration and return error message if not.

        This method provides detailed error messages explaining why a function is not eligible,
        which is useful for debugging when a @pipe_func decorated function is not being registered.

        Args:
            func: The function to check

        Returns:
            None if the function is eligible, or an error message string explaining why not
        """
        if not callable(func):
            return "not callable"

        the_function = cast("Callable[..., Any]", func)

        # Import here to avoid circular imports
        from pipelex.core.memory.working_memory import WorkingMemory  # ruff: ignore[import-outside-top-level]
        from pipelex.core.stuffs.stuff_content import StuffContent  # ruff: ignore[import-outside-top-level]

        # Get function signature
        try:
            sig = inspect.signature(the_function)
        except (ValueError, TypeError) as exc:
            return f"could not inspect signature: {exc}"

        params = list(sig.parameters.values())

        # Check parameter count
        if len(params) == 0:
            return "must have exactly one parameter named 'working_memory', but has no parameters"
        if len(params) > 1:
            return f"must have exactly one parameter named 'working_memory', but has {len(params)} parameters"

        # Check parameter name
        param = params[0]
        if param.name != "working_memory":
            return f"parameter must be named 'working_memory', but is named '{param.name}'"

        # Get type hints
        try:
            type_hints = get_type_hints(the_function)
        except (NameError, TypeError) as exc:
            return f"could not get type hints: {exc}"

        # Check parameter type annotation
        if "working_memory" not in type_hints:
            return "parameter 'working_memory' must have type annotation 'WorkingMemory'"

        param_type = type_hints["working_memory"]
        if param_type != WorkingMemory:
            return f"parameter 'working_memory' must have type 'WorkingMemory', but has type '{param_type}'"

        # Check return type annotation
        if "return" not in type_hints:
            return "must have a return type annotation that is a subclass of StuffContent"

        return_type = type_hints["return"]

        # Check if return type is a subclass of StuffContent
        try:
            if inspect.isclass(return_type) and issubclass(return_type, StuffContent):
                return None  # Eligible
            # Handle generic types like ListContent[SomeType]
            origin = get_origin(return_type)
            if inspect.isclass(origin) and issubclass(origin, StuffContent):
                return None  # Eligible
        except TypeError:
            pass

        return f"return type must be a subclass of StuffContent, but is '{return_type}'"

    def register_ineligible_function(
        self,
        func: Callable[..., Any],
        *,
        reason: str,
        source_file: str | None = None,
    ) -> None:
        """Register a function that has @pipe_func decorator but failed eligibility checks.

        This allows us to provide better error messages when the function is later looked up.

        Args:
            func: The function that failed eligibility
            reason: The reason the function is not eligible
            source_file: Optional source file path where the function was found
        """
        func_name = getattr(func, "_pipe_func_name", None) or func.__name__
        info = IneligibleFunctionInfo(func_name=func_name, reason=reason, source_file=source_file)
        self._ineligible_decorated_funcs[func_name] = info
        self.log(f"Registered ineligible @pipe_func function: {info}")

    def get_ineligible_function_info(self, name: str) -> IneligibleFunctionInfo | None:
        """Get information about an ineligible @pipe_func decorated function.

        Args:
            name: The function name to look up

        Returns:
            IneligibleFunctionInfo if the function was found but ineligible, None otherwise
        """
        return self._ineligible_decorated_funcs.get(name)


func_registry = FuncRegistry()
