import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.core.stuffs.exceptions import StoredValueUnreadableError
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.kernel.stored_value_ops import load_stored_values_through_leaf
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode

STORED_JSON_URL = "pipelex-storage://org_abc/uploads/payload/value.json"


@pytest.mark.asyncio(loop_scope="class")
class TestStoredValueOps:
    async def test_a_json_value_the_leaf_read_that_is_no_object_is_refused_naming_its_input(
        self, mocker: MockerFixture, job_metadata: JobMetadata
    ) -> None:
        """The leaf returns the stored text, and the refusal to read it as a JSON object names the input, as a load in this process does."""
        content_generator = mocker.MagicMock()
        content_generator.load_stored_texts = mocker.AsyncMock(return_value=["[1, 2, 3]"])
        mocker.patch("pipelex.kernel.stored_value_ops.get_content_generator", return_value=content_generator)

        with pytest.raises(StoredValueUnreadableError) as exc_info:
            await load_stored_values_through_leaf(
                roots={"payload": JSONContent(url=STORED_JSON_URL)},
                read_paths=None,
                job_metadata=job_metadata,
                cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
            )

        assert exc_info.value.input_name == "payload"
        assert exc_info.value.problem_params()["input"] == "payload"
        assert exc_info.value.file_type == "json"
