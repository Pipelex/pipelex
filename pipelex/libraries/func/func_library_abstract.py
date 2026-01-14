from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any


class FuncLibraryAbstract(ABC):
    @abstractmethod
    def setup(self) -> None:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass

    @abstractmethod
    def reset(self) -> None:
        pass

    @abstractmethod
    def register_function(self, func: Callable[..., Any], name: str | None = None) -> None:
        pass

    @abstractmethod
    def unregister_function(self, func: Callable[..., Any]) -> None:
        pass

    @abstractmethod
    def unregister_function_by_name(self, name: str) -> None:
        pass

    @abstractmethod
    def register_functions_dict(self, functions: dict[str, Callable[..., Any]]) -> None:
        pass

    @abstractmethod
    def register_functions(self, functions: list[Callable[..., Any]]) -> None:
        pass

    @abstractmethod
    def get_function(self, name: str) -> Callable[..., Any] | None:
        pass

    @abstractmethod
    def get_required_function(self, name: str) -> Callable[..., Any]:
        pass

    @abstractmethod
    def get_required_function_with_signature(self, name: str) -> Callable[..., object]:
        pass

    @abstractmethod
    def has_function(self, name: str) -> bool:
        pass

    @abstractmethod
    def is_marked_pipe_func(self, func: Any) -> bool:
        pass

    @abstractmethod
    def is_eligible_function(self, func: Any, require_decorator: bool = False) -> bool:
        pass
