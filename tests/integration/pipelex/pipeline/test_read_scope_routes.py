"""The routes by which a method reads a URL it chose are refused on a scoped run, and still open on an unscoped one.

A `PipeCompose` construct can build an image whose URL is assembled from plain text, with no Python
structure and no template method call, and the next `PipeLLM` shows that image to a model. On a run
with a read scope the LLM leaf refuses it before the dry-run branch, whether the URL is another
organisation's storage key or a path on the worker's disk. A bare-string image input naming a local
path is refused at the input seam, naming the input. And `pipeline_run_setup` refuses a host that
passes a read scope its storage scope does not lie under, before anything is registered.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError, iter_cause_chain
from pipelex.config import get_config
from pipelex.pipeline import pipeline_run_setup as pipeline_run_setup_module
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.storage_scope import LOCAL_STORAGE_SCOPE
from pipelex.tools.uri.exceptions import UriReadRefusalReason, UriReadRefusedError

READ_SCOPE = "org_abc"
STORAGE_SCOPE = "org_abc/mt_1/run_1"

_FORGED_PHOTO_MTHDS = """
domain = "read_scope_routes"
description = "Forge an image URL from plain text, then show the image to a model"
main_pipe = "describe_forged_photo"

[concept.Photo]
description = "A photo with a caption"

[concept.Photo.structure]
caption = { type = "text", description = "The caption" }
picture = { type = "concept", concept_ref = "native.Image", description = "The picture" }

[pipe.describe_forged_photo]
type = "PipeSequence"
description = "Forge a photo from a text, then describe it"
inputs = { where = "Text" }
output = "Text"
steps = [
  { pipe = "forge_photo", result = "photo" },
  { pipe = "describe_photo", result = "description" },
]

[pipe.forge_photo]
type = "PipeCompose"
description = "Build a photo whose URL is the text it was given"
inputs = { where = "Text" }
output = "Photo"

[pipe.forge_photo.construct]
caption = "forged"

[pipe.forge_photo.construct.picture]
url = { template = "{{ where }}" }

[pipe.describe_photo]
type = "PipeLLM"
description = "Describe the photo"
inputs = { "photo.picture" = "Image", photo = "Photo" }
output = "Text"
prompt = \"\"\"
Describe this image.
$photo.picture
\"\"\"
"""

_DESCRIBE_IMAGE_MTHDS = """
domain = "read_scope_input"
description = "Describe an image input"
main_pipe = "describe_image"

[pipe.describe_image]
type = "PipeLLM"
description = "Describe an image"
inputs = { photo = "Image" }
output = "Text"
prompt = \"\"\"
Describe this image.
$photo
\"\"\"
"""


def _find_refusal(exc: BaseException) -> UriReadRefusedError | None:
    for node in iter_cause_chain(exc):
        if isinstance(node, UriReadRefusedError):
            return node
    return None


def _protocol(*, read_scope: str | None) -> PipelexMTHDSProtocol:
    return PipelexMTHDSProtocol(
        pipe_run_mode=PipeRunMode.DRY,
        user_id="test-user",
        storage_scope=STORAGE_SCOPE if read_scope is not None else LOCAL_STORAGE_SCOPE,
        read_scope=read_scope,
    )


@pytest.mark.asyncio(loop_scope="class")
class TestReadScopeRoutes:
    @pytest.mark.parametrize(
        ("forged_url", "reason"),
        [
            ("pipelex-storage://org_other/mt_y/run_9/assets/secret.png", UriReadRefusalReason.FOREIGN_STORAGE_KEY),
            ("/etc/passwd", UriReadRefusalReason.LOCAL_PATH),
            ("file:///etc/passwd", UriReadRefusalReason.LOCAL_PATH),
        ],
    )
    async def test_a_scoped_run_refuses_the_forged_image(self, forged_url: str, reason: UriReadRefusalReason) -> None:
        with pytest.raises(PipelexError) as exc_info:
            await _protocol(read_scope=READ_SCOPE).execute(mthds_contents=[_FORGED_PHOTO_MTHDS], inputs={"where": forged_url})

        refusal = _find_refusal(exc_info.value)
        assert refusal is not None, f"expected a UriReadRefusedError in the cause chain, got {exc_info.value!r}"
        assert refusal.reason == reason
        assert "describe_photo" in refusal.message
        assert forged_url not in refusal.message

    async def test_a_scoped_run_shows_an_in_scope_image(self) -> None:
        result = await _protocol(read_scope=READ_SCOPE).execute(
            mthds_contents=[_FORGED_PHOTO_MTHDS], inputs={"where": "pipelex-storage://org_abc/assets/photo.png"}
        )
        assert result.pipe_output.main_stuff_as_str.startswith("DRY RUN:")

    @pytest.mark.parametrize("forged_url", ["pipelex-storage://org_other/mt_y/run_9/assets/secret.png", "/etc/passwd"])
    async def test_an_unscoped_run_shows_the_forged_image(self, forged_url: str) -> None:
        result = await _protocol(read_scope=None).execute(mthds_contents=[_FORGED_PHOTO_MTHDS], inputs={"where": forged_url})
        assert result.pipe_output.main_stuff_as_str.startswith("DRY RUN:")

    async def test_a_scoped_run_refuses_a_local_path_input_naming_it(self) -> None:
        with pytest.raises(UriReadRefusedError) as exc_info:
            await _protocol(read_scope=READ_SCOPE).execute(mthds_contents=[_DESCRIBE_IMAGE_MTHDS], inputs={"photo": "/etc/passwd"})
        assert exc_info.value.reason == UriReadRefusalReason.LOCAL_PATH
        assert "input 'photo'" in exc_info.value.message
        assert "/etc/passwd" not in exc_info.value.message

    @pytest.mark.parametrize(
        ("storage_scope", "match"),
        [
            (LOCAL_STORAGE_SCOPE, "must pass its own storage_scope"),
            ("org_other/mt_1/run_1", "does not lie under its read_scope"),
            ("org_abcdef/mt_1/run_1", "does not lie under its read_scope"),
        ],
    )
    async def test_a_mismatched_host_registers_no_run(self, mocker: MockerFixture, storage_scope: str, match: str) -> None:
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False)
        pipeline_manager = mocker.spy(pipeline_run_setup_module, "get_pipeline_manager")
        acquire_library = mocker.spy(pipeline_run_setup_module, "acquire_library")

        with pytest.raises(ValueError, match=match):
            await pipeline_run_setup(
                storage_scope=storage_scope,
                read_scope=READ_SCOPE,
                user_id="test-user",
                execution_config=execution_config,
                mthds_contents=[_DESCRIBE_IMAGE_MTHDS],
                pipe_code="describe_image",
            )

        pipeline_manager.assert_not_called()
        acquire_library.assert_not_called()

    async def test_an_unsafe_read_scope_registers_no_run(self, mocker: MockerFixture) -> None:
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False)
        pipeline_manager = mocker.spy(pipeline_run_setup_module, "get_pipeline_manager")

        with pytest.raises(ValueError, match="Invalid read_scope"):
            await pipeline_run_setup(
                storage_scope=STORAGE_SCOPE,
                read_scope="../org_abc",
                user_id="test-user",
                execution_config=execution_config,
                mthds_contents=[_DESCRIBE_IMAGE_MTHDS],
                pipe_code="describe_image",
            )

        pipeline_manager.assert_not_called()

    async def test_the_read_scope_rides_the_run_metadata(self) -> None:
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False)

        pipe_job, _, _ = await pipeline_run_setup(
            storage_scope=STORAGE_SCOPE,
            read_scope=READ_SCOPE,
            user_id="test-user",
            execution_config=execution_config,
            mthds_contents=[_DESCRIBE_IMAGE_MTHDS],
            pipe_code="describe_image",
        )

        assert pipe_job.job_metadata.run_metadata.read_scope == READ_SCOPE
