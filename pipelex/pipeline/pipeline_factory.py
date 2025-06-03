import shortuuid

from pipelex.pipeline.pipeline import Pipeline


class PipelineFactory:
    @classmethod
    def make_pipeline(cls) -> Pipeline:
        return Pipeline(
            pipeline_run_id=shortuuid.uuid(),
        )
