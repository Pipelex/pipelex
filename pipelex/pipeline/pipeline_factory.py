from uuid import uuid4

from pipelex import log
from pipelex.pipeline.pipeline import Pipeline


class PipelineFactory:
    @classmethod
    def make_pipeline(cls) -> Pipeline:
        pipeline_run_id = cls.make_pipeline_run_id()
        log.verbose(f"Making new pipeline with run id: {pipeline_run_id}")
        return Pipeline(
            pipeline_run_id=pipeline_run_id,
        )

    @classmethod
    def make_pipeline_run_id(cls) -> str:
        return str(uuid4())

    @classmethod
    def make_pipe_run_id(cls) -> str:
        return str(uuid4())
