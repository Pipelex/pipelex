"""The in-tree Temporal plugin (externalized to ``pipelex-temporal`` in Phase 5).

``register`` is side-effect-free and import-light — it imports no ``temporalio``:

- **always** (regardless of ``temporal.is_enabled``): contributes the TEMPORAL_*
  orchestrators and the ``worker`` / ``setup-temporal-namespace`` CLI commands.
  The orchestrator instances and command callables are import-light; the heavy
  ``temporalio`` chain is pulled lazily inside ``orchestrator.run`` and inside the
  command bodies.
- **only when ``config.temporal.is_enabled``** (i.e. boot *this* process as a
  Temporal-default runtime — a worker): claims the four process-global hub slots
  and registers the teardown callback. Each claim is a **thunk** (D5) that imports
  ``temporalio`` only when invoked at the boot apply-point, so discovering and
  registering this plugin stays import-light even on a Temporal worker (and the
  CLI-build harvest never constructs a Temporal impl).
"""

from typing import Any

from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode
from pipelex.temporal.temporal_orchestrators import TemporalBlockingOrchestrator, TemporalFireAndForgetOrchestrator


def _make_temporal_content_generator() -> Any:
    from pipelex.temporal.tprl_content_generation.content_generator_in_workflow_factory import (  # noqa: PLC0415
        ContentGeneratorInWorkflowFactory,
    )

    return ContentGeneratorInWorkflowFactory.make_content_generator_in_workflow()


def _make_temporal_pipe_router() -> Any:
    from pipelex.temporal.tprl_pipe.temporal_pipe_router import make_temporal_pipe_router  # noqa: PLC0415

    return make_temporal_pipe_router()


def _make_temporal_pipe_run() -> Any:
    from pipelex.temporal.tprl_pipe.temporal_pipe_run import make_temporal_pipe_run  # noqa: PLC0415

    return make_temporal_pipe_run()


def _setup_temporal_task_manager() -> Any:
    """Construct + wire + set up the Temporal task manager on the Temporal hub.

    Returns the task manager (the boot apply-point discards it; ``_teardown_temporal``
    re-fetches it from the Temporal hub at teardown).
    """
    from pipelex.temporal.tasks import Tasks  # noqa: PLC0415
    from pipelex.temporal.temporal_hub import temporal_hub  # noqa: PLC0415
    from pipelex.temporal.temporal_task_manager import TemporalTaskManager  # noqa: PLC0415

    task_manager = TemporalTaskManager()
    temporal_hub.set_task_manager(task_manager)
    task_manager.complement_catalog(extra_catalog=Tasks.TASK_PACKS, extra_workflows=[], extra_activities=[])
    task_manager.setup()
    return task_manager


def _teardown_temporal() -> None:
    from pipelex.temporal.temporal_hub import temporal_hub  # noqa: PLC0415

    task_manager = temporal_hub.get_optional_task_manager()
    if task_manager is not None:
        task_manager.teardown()
    temporal_hub.reset()


class TemporalPlugin:
    """Built-in plugin contributing the Temporal orchestrators, CLI commands and (when enabled) the worker runtime."""

    name = "temporal"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_orchestrator(mode=PipelexExecutionMode.TEMPORAL_BLOCKING, orchestrator=TemporalBlockingOrchestrator())
        registrar.add_orchestrator(mode=PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET, orchestrator=TemporalFireAndForgetOrchestrator())
        # CLI commands are declared by ``module:attr`` path, not by importing the callable: the command
        # modules boot Pipelex, and importing them here would cycle (builtins -> temporal_plugin ->
        # worker_cmd -> pipelex -> discovery -> builtins). The CLI layer imports them lazily at CLI-build.
        registrar.add_cli_command(
            name="worker",
            help="Start a Temporal worker for distributed workflow execution",
            import_path="pipelex.cli.commands.worker_cmd:worker_cmd",
        )
        registrar.add_cli_command(
            name="setup-temporal-namespace",
            help="Register Pipelex's custom search attributes on the configured Temporal namespace",
            import_path="pipelex.cli.commands.setup_temporal_namespace_cmd:setup_temporal_namespace_cmd",
        )

        # ``temporal.is_enabled`` means "boot this process as a Temporal-default runtime" (a worker),
        # not "the temporal plugin is on". Only then do we claim the process-global hub slots so every
        # pipe run goes through Temporal. The claims are thunks: temporalio is imported only when they
        # run at the boot apply-point, never during register.
        if registrar.config.temporal.is_enabled:
            registrar.claim_content_generator(_make_temporal_content_generator)
            registrar.claim_task_manager(_setup_temporal_task_manager)
            registrar.claim_pipe_router(_make_temporal_pipe_router)
            registrar.claim_pipe_run(_make_temporal_pipe_run)
            registrar.add_teardown(_teardown_temporal)
