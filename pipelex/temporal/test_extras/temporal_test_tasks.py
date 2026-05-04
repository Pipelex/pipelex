from pipelex.temporal.temporal_types import ActivityList, WorkflowList
from pipelex.temporal.test_extras.wf_test_child_pipe import WfTestChildPipeLLMObject, WfTestChildPipeLLMText
from pipelex.temporal.test_extras.wf_test_content_generator_child import WfTestContentGeneratorChild

TEMPORAL_TEST_WORKFLOWS: WorkflowList = [WfTestContentGeneratorChild]
TEMPORAL_TEST_ACTIVITIES: ActivityList = []


PIPELEX_TEMPORAL_TEST_WORKFLOWS: WorkflowList = [WfTestChildPipeLLMText, WfTestChildPipeLLMObject]
PIPELEX_TEMPORAL_TEST_ACTIVITIES: ActivityList = []
