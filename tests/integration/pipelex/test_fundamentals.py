import pytest

from pipelex.pipe_works.pipe_dry import dry_run_all_pipes
from pipelex.pipelex import Pipelex


# We use gha_disabled here because those tests are called directly and explicitly by the tests-check.yml file before the rest of the tests.
@pytest.mark.gha_disabled
class TestFundamentals:
    def test_boot(self):
        # This test does nothing but the conftest runs Pipelex.make()
        # Therefore this test will fail if Pipelex.make() fails.
        pass

    def test_validate_libraries(self):
        Pipelex.get_instance().validate_libraries()

    @pytest.mark.asyncio(loop_scope="class")
    async def test_dry_run_all_pipes(self):
        await dry_run_all_pipes()
