import logging
from typing import Any, Callable, Dict, List, Optional, TypeVar

from pydantic import Field, PrivateAttr, RootModel

from pipelex.tools.exceptions import ToolException
from pipelex.tools.log.log_levels import LOGGING_LEVEL_VERBOSE

FUNC_REGISTRY_LOGGER_CHANNEL_NAME = "func_registry"

# Type variable for generic function types
T = TypeVar("T")
FuncRegistryDict = Dict[str, Callable[..., Any]]


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
        name: Optional[str] = None,
        should_warn_if_already_registered: bool = True,
    ) -> None:
        """Registers a function in the registry with a name."""
        key = name or func.__name__
        if key in self.root:
            if should_warn_if_already_registered:
                self.log(f"Function '{key}' already exists in registry")
        else:
            self.log(f"Registered new single function '{key}' in registry")
        self.root[key] = func

    def unregister_function(self, func: Callable[..., Any]) -> None:
        """Unregisters a function from the registry."""
        key = func.__name__
        if key not in self.root:
            raise FuncRegistryError(f"Function '{key}' not found in registry")
        del self.root[key]
        self.log(f"Unregistered single function '{key}' from registry")

    def unregister_function_by_name(self, name: str) -> None:
        """Unregisters a function from the registry by its name."""
        if name not in self.root:
            raise FuncRegistryError(f"Function '{name}' not found in registry")
        del self.root[name]

    def register_functions_dict(self, functions: Dict[str, Callable[..., Any]]) -> None:
        """Registers multiple functions in the registry with names."""
        self.root.update(functions)
        nb_functions = len(functions)
        if nb_functions > 1:
            self.log(f"Registered {nb_functions} functions in registry")
            functions_list_str = "\n".join([f"{key}: {value.__name__}" for key, value in functions.items()])
            logging.log(level=LOGGING_LEVEL_VERBOSE, msg=functions_list_str)
        else:
            self.log(f"Registered single function '{list(functions.values())[0].__name__}' in registry")

    def register_functions(self, functions: List[Callable[..., Any]]) -> None:
        """Registers multiple functions in the registry with names."""
        if not functions:
            self.log("register_functions called with empty list of functions to register")
            return

        for func in functions:
            key = func.__name__
            if key in self.root:
                self.log(f"Function '{key}' already exists in registry, skipping")
                continue
            self.root[key] = func

        nb_functions = len(functions)
        if nb_functions > 1:
            self.log(f"Registered {nb_functions} functions in registry")
            functions_list_str = "\n".join([f"{func.__name__}: {func}" for func in functions])
            logging.log(level=LOGGING_LEVEL_VERBOSE, msg=functions_list_str)
        else:
            self.log(f"Registered single function '{functions[0].__name__}' in registry")

    def get_function(self, name: str) -> Optional[Callable[..., Any]]:
        """Retrieves a function from the registry by its name. Returns None if not found."""
        return self.root.get(name)

    def get_required_function(self, name: str) -> Callable[..., Any]:
        """Retrieves a function from the registry by its name. Raises an error if not found."""
        if name not in self.root:
            raise FuncRegistryError(f"Function '{name}' not found in registry")
        return self.root[name]

    def get_required_function_with_signature(self, name: str, expected_signature: Callable[..., T]) -> Callable[..., T]:
        """
        Retrieves a function from the registry by its name and verifies it matches the expected signature.
        Raises an error if not found or if signature doesn't match.
        """
        if name not in self.root:
            raise FuncRegistryError(f"Function '{name}' not found in registry")

        func = self.root[name]
        # Note: This is a basic signature check. For more thorough type checking,
        # you might want to use typing.get_type_hints() or a more sophisticated type checker
        if not callable(func):
            raise FuncRegistryError(f"'{name}' is not a callable function")
        return func

    def has_function(self, name: str) -> bool:
        """Checks if a function is in the registry by its name."""
        return name in self.root


func_registry = FuncRegistry()
