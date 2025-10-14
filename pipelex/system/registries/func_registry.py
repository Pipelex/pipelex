import inspect
import logging
from collections.abc import Callable
from typing import Any, TypeVar, cast, get_type_hints

from pydantic import Field, PrivateAttr, RootModel

from pipelex.system.exceptions import ToolException
from pipelex.urls import URLs

FUNC_REGISTRY_LOGGER_CHANNEL_NAME = "func_registry"

# Type variable for generic function types
T = TypeVar("T")
FuncRegistryDict = dict[str, Callable[..., Any]]

# Attribute name used by the decorator to mark functions for registration
PIPE_FUNC_MARKER = "_is_pipe_func"


class FuncRegistryError(ToolException):
    pass


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
            func._pipe_func_name = name  # type: ignore[attr-defined] # noqa: SLF001
        return func

    return decorator


class FuncRegistry(RootModel[FuncRegistryDict]):
    root: FuncRegistryDict = Field(default_factory=dict)
    _logger: logging.Logger = PrivateAttr(logging.getLogger(FUNC_REGISTRY_LOGGER_CHANNEL_NAME))

    def log(self, message: str) -> None:
        self._logger.debug(message)

    def set_logger(self, logger: logging.Logger) -> None:
        self._logger = logger

    def teardown(self) -> None:
        """Resets the registry to an empty state."""
        self.root.clear()

    def register_function(
        self,
        func: Callable[..., Any],
        name: str | None = None,
    ) -> None:
        """Registers a function in the registry with a name if it meets eligibility criteria."""
        if not self.is_eligible_function(func):
            return

        key = name or func.__name__
        if key in self.root:
            self.log(f"Function '{key}' already exists in registry")
        else:
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

    def is_eligible_function(self, func: Any, require_decorator: bool = False) -> bool:
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

        try:
            # Import here to avoid circular imports
            # TODO: code-smell
            from pipelex.core.memory.working_memory import WorkingMemory  # noqa: PLC0415
            from pipelex.core.stuffs.stuff_content import StuffContent  # noqa: PLC0415

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
                if hasattr(return_type, "__origin__"):
                    origin = return_type.__origin__
                    if inspect.isclass(origin) and issubclass(origin, StuffContent):
                        return True
            except TypeError:
                # Handle cases where issubclass fails on generic types
                pass

            return False

        except Exception:
            # If we can't analyze the function, skip it
            return False


func_registry = FuncRegistry()
