from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode


class TestPipelexExecutionMode:
    def test_string_values_are_stable(self):
        assert PipelexExecutionMode.DIRECT == "direct"
        assert PipelexExecutionMode.TEMPORAL_BLOCKING == "temporal_blocking"
        assert PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET == "temporal_fire_and_forget"
        assert PipelexExecutionMode.MISTRAL_NATIVE == "mistral_native"

    def test_requires_pipelex_temporal(self):
        assert PipelexExecutionMode.DIRECT.requires_pipelex_temporal is False
        assert PipelexExecutionMode.TEMPORAL_BLOCKING.requires_pipelex_temporal is True
        assert PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET.requires_pipelex_temporal is True
        assert PipelexExecutionMode.MISTRAL_NATIVE.requires_pipelex_temporal is False

    def test_requires_mistral_workflows_extra(self):
        assert PipelexExecutionMode.DIRECT.requires_mistral_workflows_extra is False
        assert PipelexExecutionMode.TEMPORAL_BLOCKING.requires_mistral_workflows_extra is False
        assert PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET.requires_mistral_workflows_extra is False
        assert PipelexExecutionMode.MISTRAL_NATIVE.requires_mistral_workflows_extra is True

    def test_is_fire_and_forget(self):
        assert PipelexExecutionMode.DIRECT.is_fire_and_forget is False
        assert PipelexExecutionMode.TEMPORAL_BLOCKING.is_fire_and_forget is False
        assert PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET.is_fire_and_forget is True
        assert PipelexExecutionMode.MISTRAL_NATIVE.is_fire_and_forget is False
