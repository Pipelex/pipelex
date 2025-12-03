import shortuuid

from pipelex import log
from pipelex.pipeline.pipeline import Pipeline


class PipelineFactory:
    @classmethod
    def make_pipeline(cls, pipe_code: str | None) -> Pipeline:
        short_id = shortuuid.uuid()
        pipeline_run_id = f"{pipe_code}_{short_id}" if pipe_code else short_id
        log.dev(f"Making new pipeline with run id: {pipeline_run_id}")
        return Pipeline(
            pipeline_run_id=pipeline_run_id,
        )
