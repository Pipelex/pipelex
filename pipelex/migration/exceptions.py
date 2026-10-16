from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError, PipelexSetupError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration, InheritsCause
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class MigrationError(PipelexError):
    """Base for every failure raised by the configuration-migration engine."""

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR


class MigrationRegistryError(MigrationError):
    """The surface registry is inconsistent, or names a surface that does not exist: our packaged code is wrong."""

    error_code = CoreCode.RUNTIME_UNEXPECTED


class MigrationLedgerError(MigrationError):
    """A ledger file is missing, unparseable, or internally inconsistent: our packaged ledger is wrong."""

    error_code = CoreCode.RUNTIME_UNEXPECTED


class MigrationGoldenError(MigrationError):
    """A checked-in golden is missing or unreadable, so no verdict can be produced.

    Developer tooling: only `pipelex-dev check-ledger` and the schema update reach it.
    """

    error_code = CoreCode.RUNTIME_UNEXPECTED


class MigrationSnapshotRefusedError(MigrationError):
    """The regenerator refused to overwrite a head golden that records material the models lost.

    Raised so that a habitual regeneration cannot quietly erase the very removal the coverage gate
    exists to catch. The refusal names both readings of the situation and the flag that resolves it.

    Developer tooling: only `pipelex-dev update-migration-schemas` reaches it.
    """

    error_code = CoreCode.RUNTIME_UNEXPECTED


class FunctionNamesMigrationError(PipelexError):
    """The function names of a method could not be migrated to import paths.

    Raised by `pipelex fix function-names` when the path it is handed is not a method's folder, its method tree cannot
    be listed, or a file cannot be read or written. The flat names it cannot resolve are not an error: the migration
    reports them for the author to decide.

    A path that is not a folder is ``request.invalid``, chosen where it is raised; a tree that cannot be listed
    takes the code of the error that refused it; a file that cannot be read or written is ``runtime.unexpected``.
    """

    error_code = InheritsCause(fallback=CoreCode.RUNTIME_UNEXPECTED, others=(CoreCode.REQUEST_INVALID,))


class FormerReleaseConfigError(PipelexSetupError):
    """The inference configuration still carries what a former release wrote for the Pipelex Gateway.

    Raised at boot, before the backend and routing profile libraries load, when a retired backend is enabled, a backend
    still names `model_specs_section`, or the active routing profile sends models to a retired backend. The message
    names each of them with its file, and the remedies: `pipelex migrate`, which removes what that release left and
    keeps a copy of each file it changes, and `pipelex init`, which offers the same cleanup and then sets Pipelex up
    again, on the hosted Pipelex API or on this machine.
    """

    error_code = PipelexErrorCode.CONFIG_INVALID
    # One next step for a person and an agent alike, since both read it: the human command first, then the loop an
    # agent runs, which shows the user what the cleanup would remove before it writes anything.
    user_action = UserAction(
        kind=UserActionKind.UNKNOWN,
        detail=(
            "Run 'pipelex migrate' to remove what the former release left; it keeps a copy of each file it changes or removes. "
            "From an agent, run 'pipelex-agent migrate --dry-run --format json' to see what the cleanup would remove "
            "(its 'former_release' key), show the user, then run 'pipelex-agent migrate --yes'."
        ),
    )
