import pytest

from pipelex.config import get_config
from pipelex.hub import get_pipes
from pipelex.pipe_run.dry_run import dry_run_pipes
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
        results = await dry_run_pipes(pipes=get_pipes(), raise_on_failure=False)

        # Check if there were any failures
        allowed_to_fail_pipes = get_config().pipelex.dry_run_config.allowed_to_fail_pipes

        failed_pipes = {
            pipe_code: output for pipe_code, output in results.items() if output.status.is_failure and pipe_code not in allowed_to_fail_pipes
        }

        if failed_pipes:
            failure_details = "\n".join([f"  - {pipe_code}: {output.error_message}" for pipe_code, output in failed_pipes.items()])
            pytest.fail(f"Dry run failed for {len(failed_pipes)} pipes:\n{failure_details}")
