from typing import Optional, Protocol

from typing_extensions import override

from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract


class ReportingProtocol(Protocol):
    def open_registry(self, pipeline_run_id: str): ...

    def report_inference_job(self, inference_job: InferenceJobAbstract): ...

    def generate_report(self, pipeline_run_id: Optional[str] = None): ...

    def close_registry(self, pipeline_run_id: str): ...

    def setup(self): ...

    def teardown(self): ...


class ReportingNoOp(ReportingProtocol):
    @override
    def open_registry(self, pipeline_run_id: str):
        pass

    @override
    def report_inference_job(self, inference_job: InferenceJobAbstract):
        pass

    @override
    def generate_report(self, pipeline_run_id: Optional[str] = None):
        pass

    @override
    def close_registry(self, pipeline_run_id: str):
        pass

    @override
    def setup(self):
        pass

    @override
    def teardown(self):
        pass
