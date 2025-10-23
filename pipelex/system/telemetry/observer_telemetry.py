from typing_extensions import override

from pipelex.observer.observer_protocol import ObserverProtocol, PayloadType
from pipelex.system.telemetry.events import TelemetryEventName
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract


class ObserverTelemetry(ObserverProtocol):
    def __init__(self, telemetry_manager: TelemetryManagerAbstract):
        self.telemetry_manager = telemetry_manager

    @override
    async def observe_before_run(self, payload: PayloadType) -> None:
        pipeline_run_id = payload["pipeline_run_id"]
        event_data = {
            "pipeline_run_id": pipeline_run_id,
        }
        self.telemetry_manager.track_event(event_name=TelemetryEventName.PIPE_RUN, event_data=event_data)

    @override
    async def observe_after_successful_run(self, payload: PayloadType) -> None:
        pipeline_run_id = payload["pipeline_run_id"]
        event_data = {
            "pipeline_run_id": pipeline_run_id,
            "pipe_run_outcome": "success",
        }
        self.telemetry_manager.track_event(event_name=TelemetryEventName.PIPE_COMPLETE, event_data=event_data)

    @override
    async def observe_after_failing_run(
        self,
        payload: PayloadType,
    ) -> None:
        pipeline_run_id = payload["pipeline_run_id"]
        event_data = {
            "pipeline_run_id": pipeline_run_id,
            "pipe_run_outcome": "failure",
        }
        self.telemetry_manager.track_event(event_name=TelemetryEventName.PIPE_COMPLETE, event_data=event_data)
