from typing import Dict, Optional

from pydantic import Field, RootModel
from typing_extensions import override

from pipelex.exceptions import PipelineManagerNotFoundError
from pipelex.pipeline.pipeline import Pipeline
from pipelex.pipeline.pipeline_factory import PipelineFactory
from pipelex.pipeline.pipeline_manager_abstract import PipelineManagerAbstract

PipelineManagerRoot = Dict[str, Pipeline]


class PipelineManager(PipelineManagerAbstract, RootModel[PipelineManagerRoot]):
    root: PipelineManagerRoot = Field(default_factory=dict)

    @override
    def setup(self):
        pass

    @override
    def teardown(self):
        self.root.clear()

    @override
    def get_optional_pipeline(self, pipeline_run_id: str) -> Optional[Pipeline]:
        return self.root.get(pipeline_run_id)

    @override
    def get_pipeline(self, pipeline_run_id: str) -> Pipeline:
        pipeline = self.get_optional_pipeline(pipeline_run_id=pipeline_run_id)
        if pipeline is None:
            raise PipelineManagerNotFoundError(f"Pipeline {pipeline_run_id} not found")
        return pipeline

    def _set_pipeline(self, pipeline_run_id: str, pipeline: Pipeline) -> Pipeline:
        self.root[pipeline_run_id] = pipeline
        return pipeline

    @override
    def add_new_pipeline(self) -> Pipeline:
        pipeline = PipelineFactory.make_pipeline()
        self._set_pipeline(pipeline_run_id=pipeline.pipeline_run_id, pipeline=pipeline)
        return pipeline
