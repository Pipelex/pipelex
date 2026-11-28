import pytest
from pytest_mock import MockerFixture


@pytest.fixture(autouse=True)
def no_result_line(mocker: MockerFixture) -> None:
    """The run tests here drive `PipeRun` with stand-in jobs and outputs, which hold no output to word: the result line is
    `pipelex.pipe_run.result_line`'s, tested on its own and through real runs."""
    mocker.patch("pipelex.pipe_run.pipe_run.result_line_of_run", new=mocker.AsyncMock(return_value=None))
