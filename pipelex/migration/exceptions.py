from pipelex.base_exceptions import ErrorDomain, PipelexError, PipelexSetupError


class MigrationError(PipelexError):
    """Base for every failure raised by the configuration-migration engine."""

    error_domain = ErrorDomain.CONFIG
    _declared_title = "Migration error"


class MigrationRegistryError(MigrationError):
    """The surface registry is inconsistent, or names a surface that does not exist."""

    _declared_title = "Migration registry error"


class MigrationLedgerError(MigrationError):
    """A ledger file is missing, unparseable, or internally inconsistent."""

    _declared_title = "Migration ledger error"


class MigrationGoldenError(MigrationError):
    """A checked-in golden is missing or unreadable, so no verdict can be produced."""

    _declared_title = "Migration golden error"


class MigrationSnapshotRefusedError(MigrationError):
    """The regenerator refused to overwrite a head golden that records material the models lost.

    Raised so that a habitual regeneration cannot quietly erase the very removal the coverage gate
    exists to catch. The refusal names both readings of the situation and the flag that resolves it.
    """

    _declared_title = "Migration snapshot refused"


class FormerReleaseConfigError(PipelexSetupError):
    """The inference configuration still carries what a former release wrote for the Pipelex Gateway.

    Raised at boot, before the backend and routing profile libraries load, when a retired backend is enabled, a backend
    still names `model_specs_section`, or the active routing profile sends models to a retired backend. The message
    names each of them with its file, and the remedies: `pipelex migrate`, which removes what that release left and
    keeps a copy of each file it changes, and `pipelex init`, which offers the same cleanup and then sets Pipelex up
    again, on the hosted Pipelex API or on this machine.
    """

    _declared_title = "Configuration left by a former release"
