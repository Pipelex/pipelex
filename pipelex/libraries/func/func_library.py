import inspect
from collections.abc import Callable
from typing import Any, TypeVar, cast, get_type_hints

from pydantic import Field, RootModel
from typing_extensions import override

from pipelex import log
from pipelex.libraries.func.exceptions import FuncLibraryError
from pipelex.libraries.func.func_library_abstract import FuncLibraryAbstract
from pipelex.types import Self
from pipelex.urls import URLs

# Type variable for generic function types
T = TypeVar("T")
FuncLibraryRoot = dict[str, Callable[..., Any]]

# Attribute name used by the decorator to mark functions for registration
PIPE_FUNC_MARKER = "_is_pipe_func"


def pipe_func(name: str | None = None) -> Callable[[T], T]:
    """Decorator to mark a function for automatic registration in the FuncLibrary.

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


class FuncLibrary(RootModel[FuncLibraryRoot], FuncLibraryAbstract):
    root: FuncLibraryRoot = Field(default_factory=dict)

    @override
    def setup(self) -> None:
        pass

    @override
    def teardown(self) -> None:
        """Resets the library to an empty state."""
        self.root.clear()

    @override
    def reset(self) -> None:
        self.teardown()
        self.setup()

    @classmethod
    def make_empty(cls) -> Self:
        return cls(root={})

    @override
    def register_function(
        self,
        func: Callable[..., Any],
        name: str | None = None,
    ) -> None:
        """Registers a function in the library with a name if it meets eligibility criteria."""
        if not self.is_eligible_function(func):
            return

        key = name or func.__name__
        if key in self.root:
            log.debug(f"Function '{key}' already exists in library")
        else:
            log.debug(f"Registered new single function '{key}' in library")
        self.root[key] = func

    @override
    def get_function(self, name: str) -> Callable[..., Any] | None:
        """Retrieves a function from the library by its name. Returns None if not found."""
        return self.root.get(name)

    @override
    def get_required_function(self, name: str) -> Callable[..., Any]:
        """Retrieves a function from the library by its name. Raises an error if not found."""
        if name not in self.root:
            msg = (
                f"Function '{name}' not found in library. "
                f"Since v0.12.0, custom functions require the @pipe_func() decorator for auto-discovery. "
                f"Add @pipe_func() above your function definition. "
                f"See: {URLs.pipe_func_docs}"
            )
            raise FuncLibraryError(msg)
        return self.root[name]

    @override
    def has_function(self, name: str) -> bool:
        """Checks if a function is in the library by its name."""
        return name in self.root

    @override
    def is_marked_pipe_func(self, func: Any) -> bool:
        """Checks if a function is marked with the @pipe_func decorator.

        Args:
            func: The function to check

        Returns:
            True if the function has the pipe_func marker attribute

        """
        return hasattr(func, PIPE_FUNC_MARKER) and getattr(func, PIPE_FUNC_MARKER) is True

    # TODO: refactor this into a subclass of FuncLibrary dedicated to pipe funcs, avoid the circular import issue, avoid the code-smell
    @override
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
