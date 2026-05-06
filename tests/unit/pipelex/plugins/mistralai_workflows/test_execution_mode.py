from pipelex.plugins.mistralai_workflows.execution_mode import PipelexExecutionMode


class TestPipelexExecutionMode:
    def test_string_values_are_stable(self):
        assert PipelexExecutionMode.DIRECT == "direct"
        assert PipelexExecutionMode.TEMPORAL_BLOCKING == "temporal_blocking"
        assert PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET == "temporal_fire_and_forget"

    def test_requires_pipelex_temporal(self):
        assert PipelexExecutionMode.DIRECT.requires_pipelex_temporal is False
        assert PipelexExecutionMode.TEMPORAL_BLOCKING.requires_pipelex_temporal is True
        assert PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET.requires_pipelex_temporal is True

    def test_is_fire_and_forget(self):
        assert PipelexExecutionMode.DIRECT.is_fire_and_forget is False
        assert PipelexExecutionMode.TEMPORAL_BLOCKING.is_fire_and_forget is False
        assert PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET.is_fire_and_forget is True
