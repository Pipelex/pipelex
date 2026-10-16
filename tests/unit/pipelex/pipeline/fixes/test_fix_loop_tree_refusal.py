from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.pipeline.fixes.fix_loop import fix_bundle_file

_BUNDLE = """domain = "fix_tree_refusal"
main_pipe = "write_notice"

[pipe.write_notice]
type = "PipeLLM"
description = "Write a notice"
inputs = { topic = "Text" }
output = "Text"
prompt = "Write about $topic"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestFixLoopTreeRefusal:
    async def test_a_library_tree_that_cannot_be_listed_is_the_invalid_verdict_with_nothing_to_fix(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """The snapshot lists the method's trees before validating: a refused tree ends the loop with its message, never an exception."""
        library_dir = tmp_path / "library"
        library_dir.mkdir()
        bundle_path = library_dir / "notice.mthds"
        bundle_path.write_text(_BUNDLE, encoding="utf-8")
        (library_dir / "linked_notice.mthds").symlink_to(bundle_path)
        validate_mock = mocker.patch("pipelex.pipeline.fixes.fix_loop.validate_bundle")

        result = await fix_bundle_file(bundle_path, library_dirs=[library_dir], max_iterations=3)

        assert result.is_valid is False
        assert result.iterations == 0
        assert result.files_written == []
        (item,) = result.remaining_errors
        assert "linked_notice.mthds" in item.message
        validate_mock.assert_not_called()
        assert bundle_path.read_text(encoding="utf-8") == _BUNDLE
