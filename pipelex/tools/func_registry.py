import inspect
import logging
from collections.abc import Callable
from typing import Any, TypeVar, get_type_hints

from pydantic import Field, PrivateAttr, RootModel

from pipelex.tools.exceptions import ToolException

FUNC_REGISTRY_LOGGER_CHANNEL_NAME = "func_registry"

# Type variable for generic function types
T = TypeVar("T")
FuncRegistryDict = dict[str, Callable[..., Any]]


class FuncRegistryError(ToolException):
    pass


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
        should_warn_if_already_registered: bool = True,
    ) -> None:
        """Registers a function in the registry with a name if it meets eligibility criteria."""
        if not self.is_eligible_function(func):
            return

        key = name or func.__name__
        if key in self.root:
            if should_warn_if_already_registered:
                self.log(f"Function '{key}' already exists in registry")
            else:
                msg = f"Function '{key}' already exists in registry"
                raise FuncRegistryError(msg)
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
            self.register_function(func=func, name=name, should_warn_if_already_registered=False)

    def register_functions(self, functions: list[Callable[..., Any]]) -> None:
        """Registers multiple functions in the registry with names if they meet eligibility criteria."""
        for func in functions:
            self.register_function(func=func, should_warn_if_already_registered=False)

    def get_function(self, name: str) -> Callable[..., Any] | None:
        """Retrieves a function from the registry by its name. Returns None if not found."""
        return self.root.get(name)

    def get_required_function(self, name: str) -> Callable[..., Any]:
        """Retrieves a function from the registry by its name. Raises an error if not found."""
        if name not in self.root:
            msg = (
                f"Function '{name}' not found in registry:"
                "See how to register a function here: https://docs.pipelex.com/pages/build-reliable-ai-workflows-with-pipelex/pipe-operators/PipeFunc"
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

    def is_eligible_function(self, func: Callable[..., Any]) -> bool:
        """Checks if a function matches the criteria for PipeFunc registration:
        - Exactly 1 parameter named "working_memory" with type WorkingMemory
        - Return type that is a subclass of StuffContent
        """
        try:
            # Import here to avoid circular imports
            from pipelex.core.memory.working_memory import WorkingMemory  # noqa: PLC0415
            from pipelex.core.stuffs.stuff_content import StuffContent  # noqa: PLC0415

            # Get function signature
            sig = inspect.signature(func)
            params = list(sig.parameters.values())

            # Check parameter count and name
            if len(params) != 1:
                return False

            param = params[0]
            if param.name != "working_memory":
                return False

            # Get type hints
            type_hints = get_type_hints(func)

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
