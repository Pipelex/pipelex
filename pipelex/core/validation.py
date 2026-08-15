from pydantic import ValidationError

from pipelex.tools.typing.pydantic_utils import analyze_pydantic_validation_error


def report_validation_error(*, validation_error: ValidationError) -> str:
    """Render a pydantic validation error as the friendly message a user reads.

    Runs before and around bootstrap — the doctor calls it from inside its own bootstrap, where
    the hub's config may still be unset — so it reads no configuration and must keep that property.

    It used to append rename hints drawn from ``[migration.migration_maps.*]`` in ``pipelex.toml``.
    That table is gone: renames are now recorded as migration-ledger entries, and the migrator
    reports them from a real plan rather than from a hand-maintained map of old and new spellings.
    """
    return analyze_pydantic_validation_error(validation_error).error_msg
