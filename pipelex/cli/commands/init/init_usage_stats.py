"""What an `init` command set, noted for its `command_completed`: where runs execute and which backends it enabled.

Both `pipelex init` and `pipelex-agent init` note each choice once the file holding it is written, so a setup that
stops partway reports only what it set. Backend keys are reported by the provider names `model_used` uses, a backend
pipelex does not ship counting as `custom`.
"""

from collections.abc import Iterable

from pipelex.hosted.run_config import RunExecution
from pipelex.system.usage_stats.usage_stats_client import note_command_init_choices
from pipelex.system.usage_stats.usage_stats_contract import UsageStatsInitExecution, UsageStatsProvider
from pipelex.system.usage_stats.usage_stats_events import InitChoices


def note_init_execution(*, execution: RunExecution) -> None:
    """Note where this `init` set runs to execute."""
    init_execution: UsageStatsInitExecution
    match execution:
        case RunExecution.LOCAL:
            init_execution = UsageStatsInitExecution.LOCAL
        case RunExecution.HOSTED:
            init_execution = UsageStatsInitExecution.HOSTED
    note_command_init_choices(init_choices=InitChoices(execution=init_execution))


def note_init_backends(*, backend_keys: Iterable[str]) -> None:
    """Note the backends this `init` left enabled, every other one counting as not enabled."""
    providers = frozenset(UsageStatsProvider.for_backend(backend_name=backend_key) for backend_key in backend_keys)
    note_command_init_choices(init_choices=InitChoices(enabled_providers=providers))
