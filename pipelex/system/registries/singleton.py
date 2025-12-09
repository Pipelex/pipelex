from abc import ABCMeta
from typing import Any, ClassVar, TypeVar

from typing_extensions import override

T = TypeVar("T")


class MetaSingleton(type):
    """Simple implementation of a singleton using a metaclass."""

    instances: ClassVar[dict[type[Any], Any]] = {}

    @override
    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls.instances:  # pyright: ignore[reportUnnecessaryContains]
            cls.instances[cls] = super().__call__(*args, **kwargs)
        return cls.instances[cls]

    @classmethod
    def clear_subclass_instances(cls, base_cls: type[Any]) -> None:
        """Clear all instances of subclasses of base_cls from the registry."""
        for subclass in list(cls.instances.keys()):
            if issubclass(subclass, base_cls):
                del cls.instances[subclass]

    @classmethod
    def get_subclass_instance(cls, base_cls: type[T]) -> T | None:
        """Get the singleton instance of a subclass of base_cls.

        This is useful when the base class is abstract and only concrete
        subclasses are instantiated.
        """
        for subclass, instance in cls.instances.items():
            if issubclass(subclass, base_cls) and isinstance(instance, base_cls):
                return instance
        return None


class ABCSingletonMeta(ABCMeta, MetaSingleton):
    """Combined metaclass for ABC + Singleton pattern."""
