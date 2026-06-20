from pipelex.base_exceptions import PipelexError


class TemporalConfigError(PipelexError, ValueError):
    """Raised when the ``[temporal]`` configuration section is invalid.

    Lives in core — outside the externalizable ``pipelex_temporal`` package — so
    the Temporal config *schema* (``config_temporal.py``, imported unconditionally
    by ``configs.py``) can raise it without the core config-load path depending on
    ``pipelex_temporal``. The Temporal runtime's own config-error subclasses
    (``WorkerScopeConfigError``, ``WorkerProfileConfigError``,
    ``SearchAttributeRegistrationError``) subclass this from
    ``pipelex_temporal.exceptions``.
    """


class WorkerTaskQueueUnknownError(TemporalConfigError):
    """Raised when a ``--task-queue`` value is not declared anywhere in the Temporal config."""
