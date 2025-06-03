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
    def get_optional_mission(self, mission_id: str) -> Optional[Pipeline]:
        return self.root.get(mission_id)

    @override
    def get_mission(self, mission_id: str) -> Pipeline:
        mission = self.get_optional_mission(mission_id=mission_id)
        if mission is None:
            raise PipelineManagerNotFoundError(f"Pipeline {mission_id} not found")
        return mission

    def _set_mission(self, mission_id: str, mission: Pipeline) -> Pipeline:
        self.root[mission_id] = mission
        return mission

    @override
    def add_new_mission(self) -> Pipeline:
        mission = PipelineFactory.make_mission()
        self._set_mission(mission_id=mission.pipeline_run_id, mission=mission)
        return mission
