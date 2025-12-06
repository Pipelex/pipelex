from pipelex import log
from pipelex.pipeline.pipeline import Pipeline
from pipelex.pipeline.run_id_factory import make_pipeline_run_id


class PipelineFactory:
    @classmethod
    def make_pipeline(cls, pipe_code: str | None) -> Pipeline:
        pipeline_run_id = make_pipeline_run_id(pipe_code)
        log.dev(f"Making new pipeline with run id: {pipeline_run_id}")
        return Pipeline(
            pipeline_run_id=pipeline_run_id,
        )
