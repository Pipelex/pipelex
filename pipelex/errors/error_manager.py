from typing import Protocol

from pipelex.system.registries.singleton import ABCSingletonMeta, MetaSingleton


class _ErrorsConfigLike(Protocol):
    """Structural type for the config object held by :class:`ErrorManager`.

    Declared locally rather than imported from
    :mod:`pipelex.errors.errors_config` so this module retains zero transitive
    dependency on the configuration / ``ConfigModel`` layer (which would
    re-enter :mod:`pipelex.base_exceptions` via :mod:`pipelex.system.exceptions`,
    forming a static import cycle). The concrete config class
    (:class:`pipelex.errors.errors_config.ErrorsConfig`) satisfies this
    protocol structurally — Pydantic models match Protocols by attribute
    presence — and the call site in :class:`pipelex.pipelex.Pipelex` passes a
    fully constructed instance in.

    ``base_uri`` is declared as a read-only ``@property`` so the Protocol matches
    Pydantic models constructed with ``ConfigDict(frozen=True)`` (where the field
    is read-only at runtime).
    """

    @property
    def base_uri(self) -> str: ...


class ErrorManager(metaclass=ABCSingletonMeta):
    """Singleton registry for error-rendering settings.

    Constructed during Pipelex bootstrap from
    :class:`pipelex.errors.errors_config.ErrorsConfig`. Consumed by
    :meth:`pipelex.base_exceptions.PipelexError.type_uri` to derive RFC 7807
    ``type`` URIs without importing ``pipelex.hub`` (avoids a static import
    cycle — same reason :class:`pipelex.graph.graph_tracer_manager.GraphTracerManager`
    uses this pattern).

    Lifecycle contract: do NOT call ``ErrorManager(...)`` directly outside
    :meth:`pipelex.pipelex.Pipelex.__init__`. Reads must go through
    :meth:`get_required_instance`; tests that need to drop the singleton
    must restore it (see :meth:`clear_instance`).
    """

    def __init__(self, errors_config: _ErrorsConfigLike) -> None:
        self._errors_config = errors_config

    @property
    def base_uri(self) -> str:
        """The error documentation base URI, normalized (no trailing slash) by ``ErrorsConfig``."""
        return self._errors_config.base_uri

    @classmethod
    def get_instance(cls) -> "ErrorManager | None":
        """Return the singleton instance, or ``None`` when Pipelex bootstrap has not run."""
        return MetaSingleton.get_subclass_instance(ErrorManager)

    @classmethod
    def get_required_instance(cls) -> "ErrorManager":
        """Return the singleton instance, raising ``RuntimeError`` when bootstrap has not run."""
        instance = cls.get_instance()
        if instance is None:
            msg = "ErrorManager is not initialized — Pipelex bootstrap must run first"
            raise RuntimeError(msg)
        return instance

    @classmethod
    def clear_instance(cls) -> None:
        """Clear the singleton instance from the ``MetaSingleton`` registry."""
        MetaSingleton.clear_subclass_instances(ErrorManager)
