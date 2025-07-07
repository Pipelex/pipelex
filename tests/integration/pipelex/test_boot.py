import pytest

from pipelex.hub import get_pipe_provider
from pipelex.pipe_works.pipe_dry import dry_run_pipes


@pytest.mark.asyncio(loop_scope="class")
class TestBoot:
    async def test_boot(self):
        # This test does nothing but the conftest runs Pipelex.make() with the dryrun
        # Therefore this test will fail if Pipelex.make() fails.
        await dry_run_pipes(get_pipe_provider().get_pipes())
