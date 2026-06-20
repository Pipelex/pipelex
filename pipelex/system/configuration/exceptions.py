from pipelex.base_exceptions import PipelexError


class TemporalConfigError(ValueError, PipelexError):
    """Raised when the ``[temporal]`` configuration section is invalid.

    Lives in core — outside the externalizable ``pipelex.temporal`` package — so
    the Temporal config *schema* (``config_temporal.py``, imported unconditionally
    by ``configs.py``) can raise it without the core config-load path depending on
    ``pipelex.temporal``. The Temporal runtime's own config-error subclasses
    (``WorkerScopeConfigError``, ``WorkerProfileConfigError``,
    ``SearchAttributeRegistrationError``) subclass this from
    ``pipelex.temporal.exceptions``.
    """


class WorkerTaskQueueUnknownError(TemporalConfigError):
    """Raised when a ``--task-queue`` value is not declared anywhere in the Temporal config."""
