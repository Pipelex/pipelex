import pytest

from pipelex.hub import get_inference_manager


@pytest.mark.gha_disabled
@pytest.mark.codex_disabled
class TestCogtSetupWorkers:
    def test_setup_inference_manager(self):
        get_inference_manager().setup_llm_workers()
        get_inference_manager().setup_imgg_workers()
