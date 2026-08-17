"""Translating a validation failure into something a person can act on.

Two things can be wrong when a model refuses a document, and they call for opposite next moves.
The document may be *wrong* — a typo, a value out of range, a field that was never a field — and
then the pydantic analysis is the whole answer. Or the document may simply be *old*: written
against a schema this build has since moved past, in which case nothing about it is a mistake and
the remedy is a command rather than an edit.

Only the second case needs anything beyond the translation, and only a configuration surface can
be in it — so a caller that knows which surface refused says so, and this module asks the
migration ledger what a `pipelex migrate` would find. What comes back rides the error twice: as a
sentence in the message a human reads, and as the structured `migration` block a machine consumer
branches on.

> **A scan is a diagnosis, never a repair.** Nothing here writes; the remedy is a command the user
> runs. See `docs/migration-ledger.md` → "Reporting a stale configuration on a validation error".
"""

from pathlib import Path
from typing import NoReturn

from pydantic import BaseModel, ConfigDict, ValidationError

from pipelex.base_exceptions import MigrationErrorBlock, PipelexConfigError
from pipelex.migration.exceptions import MigrationError
from pipelex.migration.plan import MigrationPlan
from pipelex.system.configuration.config_loader import pydantic_error_behind
from pipelex.tools.typing.pydantic_utils import analyze_pydantic_validation_error

MIGRATE_COMMAND = "pipelex migrate"


class ValidationErrorReport(BaseModel):
    """A refused document, said twice: once as prose and once as structure.

    The two halves are the same answer for two readers, and the structured one is the contract —
    a consumer branches on `migration` being present, never on the wording of `message`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    message: str
    """The pydantic analysis, plus a paragraph about the pending migration when there is one."""

    migration: MigrationErrorBlock | None = None
    """What a `pipelex migrate` would find for the surface that refused, when a scan found
    anything at all. `None` means the failure is not staleness — or that no surface was named."""


def report_validation_error(
    *,
    validation_error: ValidationError,
    surface_id: str | None = None,
    config_dirs: list[Path] | None = None,
) -> ValidationErrorReport:
    """Translate a validation failure, and say so when a pending migration would explain it.

    Args:
        validation_error: The pydantic error to translate.
        surface_id: The configuration surface whose model refused, when one did. Naming it is what
            turns on the migration scan; a caller validating something that is not a configuration
            surface — a `.mthds` bundle, an inference backend file, a model deck — passes nothing
            and gets the translation alone.
        config_dirs: The directories the refused configuration was loaded from, when the caller
            bypassed the global/project layering (`doctor --global`, an embedder's `config_dir=`).
            The scan then diagnoses those and only those; `None` is the ordinary load, and the
            scan walks what `pipelex migrate` walks.

    Returns:
        The translated message and, when a scan found something, the structured migration block.
    """
    message = analyze_pydantic_validation_error(validation_error).error_msg
    if surface_id is None:
        return ValidationErrorReport(message=message)
    block = _pending_migration(surface_id=surface_id, config_dirs=config_dirs)
    if block is None:
        return ValidationErrorReport(message=message)
    return ValidationErrorReport(message=f"{message}\n\n{_migration_prose(block=block)}", migration=block)


def raise_config_setup_error(*, config_error: Exception, surface_id: str, config_dirs: list[Path] | None = None) -> NoReturn:
    """Turn a refused configuration into the `PipelexConfigError` a caller should see, migration and all.

    Shared by every site that loads a configuration surface and cannot continue without it, so
    that the same refusal produces the same message and the same structured block wherever it is
    caught. Doing it by hand per site is how one of them came to catch only pydantic's error and
    stop reporting anything at all for the main configuration.

    A refusal carrying no pydantic error is re-raised untouched: there is no field-level analysis
    to translate, and its own message is already the whole account.

    Args:
        config_error: The refusal, either half of `CONFIG_REFUSED`.
        surface_id: The configuration surface that refused, which is what turns on the scan.
        config_dirs: The directories the configuration was loaded from, when the caller named
            them — see `report_validation_error`.

    Raises:
        PipelexConfigError: Always, unless `config_error` is re-raised as itself.
    """
    validation_error = pydantic_error_behind(config_error=config_error)
    if validation_error is None:
        raise config_error
    report = report_validation_error(validation_error=validation_error, surface_id=surface_id, config_dirs=config_dirs)
    msg = f"Could not setup config because of: {report.message}"
    raise PipelexConfigError(msg, migration=report.migration) from config_error


def _pending_migration(*, surface_id: str, config_dirs: list[Path] | None) -> MigrationErrorBlock | None:
    """What a `pipelex migrate` would find for this surface, or `None` when it would find nothing.

    Runs on the failure path only, which is what lets it be a filesystem walk and a ledger replay
    at all: a boot whose configuration validates never reaches this module.

    **Nothing that goes wrong inside the scan may become the failure the user sees.** They have a
    configuration error in front of them and it names what to fix; replacing it with a packaging
    problem of ours would cost them the only message that helps. A ledger that will not load is
    loud where it should be loud — `make check-ledger`, and the `migrate` command itself. The
    catch is deliberately narrow rather than a blanket one: an applier bug raises neither of these
    and should keep surfacing as the bug it is.
    """
    # Imported here rather than at module level, and the reason is architectural, not lazy: the
    # migration engine's applier lives under `pipelex.pipeline`, an interpreter package, while
    # this module sits in `runtime_boot`'s import closure — the kernel layer, whose stated
    # property is that importing it loads zero interpreter modules. `make agent-check` would not
    # catch a module-level import here; only the full `make agent-test` would.
    from pipelex.migration.run import scan_config_surface  # noqa: PLC0415

    try:
        report = scan_config_surface(surface_id=surface_id, config_dirs=config_dirs)
    except (MigrationError, OSError):
        return None
    plans = [plan for plan in report.plans if not plan.is_clean]
    if not plans:
        return None
    return MigrationErrorBlock(
        remedy=MIGRATE_COMMAND,
        would_write=any(plan.did_change for plan in plans),
        needs_attention=report.needs_attention,
        plans=plans,
    )


def _migration_prose(*, block: MigrationErrorBlock) -> str:
    """The block as a paragraph, for the reader who gets the message rather than the fields.

    Says the same things as the boot-tolerance warning and in the same order, because the two are
    read in the same places and describe the same machine — the difference is only that this one
    is attached to a failure rather than to a boot that carried on. Everything it names comes from
    the ledger or from a file path: **no value read from a user's file appears here**, which is
    the third of the three channels that rule covers.

    **The paragraph opens and closes on `would_write`, never on the block's presence.** A block
    means the migration history has something to say about these files; only `would_write` means
    the command would change them. Telling a reader to run a migration over a file it would not
    touch is a sentence whose honest outcome is *nothing was written*, with their error still in
    front of them — so on that side the paragraph says so and points at the dry run, which is where
    the diagnosis is. And when the command would write but the paragraph has just listed what it
    cannot do, the closing sentence says both, rather than promising a repair the list above has
    already qualified.
    """
    files = ", ".join(f"'{plan.file_path}'" for plan in block.plans)
    carried = sorted({step.title for plan in block.plans for step in plan.steps})
    if block.would_write:
        sentences = [f"Your configuration may be out of date rather than wrong: {files}."]
    else:
        sentences = [f"The migration history has something to say about these files: {files}."]
    if carried:
        sentences.append(f"What `{block.remedy}` would carry forward: {'; '.join(carried)}.")
    unresolved = _what_needs_a_person(plans=block.plans)
    if unresolved:
        sentences.append(f"What it cannot do for you: {'; '.join(unresolved)}.")
    if block.would_write and unresolved:
        sentences.append(f"Run `{block.remedy}` to carry forward what it can; the rest is yours to fix.")
    elif block.would_write:
        sentences.append(f"Run `{block.remedy}` to bring these files up to date.")
    else:
        sentences.append(
            f"`{block.remedy}` would rewrite nothing here — run `{block.remedy} --dry-run` to read what it found, and fix these files by hand."
        )
    return " ".join(sentences)


def _what_needs_a_person(*, plans: list[MigrationPlan]) -> list[str]:
    """Everything in the scan a command will not resolve, each said once and in file order."""
    unresolved: list[str] = []
    for plan in plans:
        where = _file_name(file_path=plan.file_path)
        if plan.blocked_reason is not None:
            unresolved.append(f"{where} could not be read as configuration ({plan.blocked_reason})")
        unresolved.extend(f"{where} needs '{entry.entry_id}' applied by hand ({entry.reason})" for entry in plan.blocked)
        unresolved.extend(f"{where} sets '{unexplained.path}', which this build knows nothing about" for unexplained in plan.unexplained)
    return unresolved


def _file_name(*, file_path: Path) -> str:
    """A file named the way a sentence names it — the leaf, since the paths were listed already."""
    return f"'{file_path.name}'"
