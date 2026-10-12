"""The warnings a validation sweep collects from the dry runs it makes.

A dry run can find something an author should hear about without failing: the warning findings of a
`PipeDocGen` step's template check are the first such thing. They belong in the verdict's advisory
`warnings`, beside the static lints, and the verdict is composed long after the pipe that found them has
returned. So a sweep whose caller reports them (`collect_dry_run_warnings`, which the validate surfaces pass)
collects them while each pipe's dry run is in flight, and keeps them on that pipe's `DryRunOutput`, from which
the composition point reads them (`pipelex.pipeline.advisory_warnings`).

The collector is a context variable, scoped by the sweep to one pipe's dry run, for the same reasons the
sweep's failure recorder is one: the asyncio tasks a controller's fan-out spawns inherit it, so a pipe run
deep inside a sequence or a batch reports to the same collector, and concurrent sweeps never mix.

A dry run that no sweep collects has no verdict to put a warning in, and its pipe logs the warning instead
(see :func:`report_dry_run_warning`): `pipelex run --dry-run`, and every sweep whose caller reports no verdict
of its own, such as `pipelex fix bundle` or `pipelex build inputs`, so no warning is dropped unseen. The graph arm of a validation dry-runs
its target again after the sweep, and collects what it finds only to drop it, since the sweep reported it.
"""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

from pipelex.base_exceptions import ValidationErrorItem


class DryRunWarningCollector:
    """The warnings one pipe's dry run found, in the order they were found, each once.

    A pipe can be run several times within one dry run, such as a step a batch runs for each item, and each
    run finds the same warning again; it is kept once.
    """

    def __init__(self) -> None:
        self._warnings: list[ValidationErrorItem] = []

    def add(self, *, warning: ValidationErrorItem) -> None:
        if warning not in self._warnings:
            self._warnings.append(warning)

    @property
    def warnings(self) -> list[ValidationErrorItem]:
        return list(self._warnings)


_dry_run_warning_collector: ContextVar[DryRunWarningCollector | None] = ContextVar("dry_run_warning_collector", default=None)


@contextmanager
def collecting_dry_run_warnings() -> Generator[DryRunWarningCollector, None, None]:
    """Collect the warnings of the dry runs made inside this scope, for the sweep that opened it."""
    collector = DryRunWarningCollector()
    token = _dry_run_warning_collector.set(collector)
    try:
        yield collector
    finally:
        _dry_run_warning_collector.reset(token)


def report_dry_run_warning(*, warning: ValidationErrorItem) -> bool:
    """Hand a warning to the sweep collecting this dry run's warnings.

    Returns:
        True when a sweep took it for its caller's verdict; False when no sweep collects this dry run's warnings,
        in which case the caller logs it, since nothing else will report it.
    """
    collector = _dry_run_warning_collector.get()
    if collector is None:
        return False
    collector.add(warning=warning)
    return True
