from typing import Protocol

from typing_extensions import override

from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.tracing.event_log_protocol import EventLogProtocol


class ReportingProtocol(Protocol):
    def report_inference_job(self, inference_job: InferenceJobAbstract): ...

    def setup(self): ...

    def teardown(self): ...

    def set_event_log(
        self,
        context_key: str,
        *,
        event_log: EventLogProtocol,
        workflow_id: str,
        pipeline_run_id: str,
    ) -> None: ...

    def clear_event_log(self, context_key: str) -> None: ...


class ReportingNoOp(ReportingProtocol):
    @override
    def report_inference_job(self, inference_job: InferenceJobAbstract):
        pass

    @override
    def setup(self):
        pass

    @override
    def teardown(self):
        pass

    @override
    def set_event_log(
        self,
        context_key: str,
        *,
        event_log: EventLogProtocol,
        workflow_id: str,
        pipeline_run_id: str,
    ) -> None:
        pass

    @override
    def clear_event_log(self, context_key: str) -> None:
        pass
