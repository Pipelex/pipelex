from typing_extensions import override

from pipelex.observer.observer_protocol import ObserverProtocol, PayloadKey, PayloadType
from pipelex.system.telemetry.events import EventName, EventProperty, Outcome
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract


class ObserverTelemetry(ObserverProtocol):
    def __init__(self, telemetry_manager: TelemetryManagerAbstract):
        self.telemetry_manager = telemetry_manager

    @override
    async def observe_before_run(self, payload: PayloadType) -> None:
        pipe_job = payload[PayloadKey.PIPE_JOB]
        properties = {
            EventProperty.PIPELINE_RUN_ID: payload[PayloadKey.PIPELINE_RUN_ID],
            EventProperty.PIPE_TYPE: pipe_job.pipe_type,
        }
        self.telemetry_manager.track_event(event_name=EventName.PIPE_RUN, properties=properties)

    @override
    async def observe_after_successful_run(self, payload: PayloadType) -> None:
        pipe_job = payload[PayloadKey.PIPE_JOB]
        properties = {
            EventProperty.PIPELINE_RUN_ID: payload[PayloadKey.PIPELINE_RUN_ID],
            EventProperty.PIPE_TYPE: pipe_job.pipe_type,
            EventProperty.PIPE_RUN_OUTCOME: Outcome.SUCCESS,
        }
        self.telemetry_manager.track_event(event_name=EventName.PIPE_COMPLETE, properties=properties)

    @override
    async def observe_after_failing_run(
        self,
        payload: PayloadType,
    ) -> None:
        pipe_job = payload[PayloadKey.PIPE_JOB]
        properties = {
            EventProperty.PIPELINE_RUN_ID: payload[PayloadKey.PIPELINE_RUN_ID],
            EventProperty.PIPE_TYPE: pipe_job.pipe_type,
            EventProperty.PIPE_RUN_OUTCOME: Outcome.FAILURE,
        }
        self.telemetry_manager.track_event(event_name=EventName.PIPE_COMPLETE, properties=properties)
