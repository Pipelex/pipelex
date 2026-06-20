from pipelex.types import StrEnum


class PipelexExecutionMode(StrEnum):
    """How a Pipelex pipe runs inside a host runtime activity.

    DIRECT: in-process; no Temporal involved on Pipelex's side; activity blocks
        until the pipe completes. Fastest feedback, simplest ops.
    TEMPORAL_BLOCKING: dispatch the pipe as a Pipelex Temporal workflow; the
        activity awaits completion. Pipe runs durably on Pipelex's worker
        fleet. Requires the pipelex-temporal plugin.
    TEMPORAL_FIRE_AND_FORGET: dispatch the pipe as a Pipelex Temporal workflow
        and return immediately with the workflow_id. Activity does NOT wait;
        completion is signalled out-of-band via DeliveryAssignment (webhook /
        storage). Same dep requirements as TEMPORAL_BLOCKING.
        ``delivery_assignment_dump`` is required.
    MISTRAL_NATIVE: decompose the pipe into native Mistral Workflows primitives
        on the same worker — controllers as child workflows, leaves as
        activities. Surfaces per-step retry / signals / cancellation through
        the host-runtime APIs. Requires the
        ``pipelex-mistralai-workflows`` package.
    """

    DIRECT = "direct"
    TEMPORAL_BLOCKING = "temporal_blocking"
    TEMPORAL_FIRE_AND_FORGET = "temporal_fire_and_forget"
    MISTRAL_NATIVE = "mistral_native"

    @property
    def requires_pipelex_temporal(self) -> bool:
        match self:
            case PipelexExecutionMode.DIRECT | PipelexExecutionMode.MISTRAL_NATIVE:
                return False
            case PipelexExecutionMode.TEMPORAL_BLOCKING | PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET:
                return True

    @property
    def requires_mistral_workflows_extra(self) -> bool:
        match self:
            case PipelexExecutionMode.MISTRAL_NATIVE:
                return True
            case PipelexExecutionMode.DIRECT | PipelexExecutionMode.TEMPORAL_BLOCKING | PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET:
                return False

    @property
    def is_fire_and_forget(self) -> bool:
        match self:
            case PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET:
                return True
            case PipelexExecutionMode.DIRECT | PipelexExecutionMode.TEMPORAL_BLOCKING | PipelexExecutionMode.MISTRAL_NATIVE:
                return False
