from pathlib import Path

import pytest
import tomlkit
from pytest_mock import MockerFixture

from pipelex.core.exceptions import PipesAndConceptValidationErrorData
from pipelex.libraries.method_tree_listing import MethodTreeListing
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.fixes import fix_loop
from pipelex.pipeline.fixes.fix_loop import fix_method_folder
from pipelex.validation_error_types import PipeValidationErrorType

_IDEAS_MTHDS = """domain = "folder_fix_ideas"
main_pipe = "list_ideas"

[pipe.list_ideas]
type = "PipeLLM"
description = "Lists ideas, declaring a single Text where its sequence makes several."
inputs = { topic = "Text" }
output = "Text"
prompt = "Write about $topic"
"""

_SUMMARY_MTHDS = """domain = "folder_fix_summary"
main_pipe = "summarize"

[pipe.summarize]
type = "PipeLLM"
description = "A second bundle declaring its own main pipe, so the folder decides no entry."
inputs = { topic = "Text" }
output = "Text"
prompt = "Summarize $topic"
"""


def _seq_output_error(*, source: str | None) -> ValidateBundleError:
    return ValidateBundleError(
        message="Pipe validation failed",
        pipe_validation_errors=[
            PipesAndConceptValidationErrorData(
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                domain_code="folder_fix_ideas",
                source=source,
                pipe_code="list_ideas",
                message="pipe 'list_ideas' output mismatch",
                field_path=source or "",
                expected_output_ref="Idea[]",
            ),
        ],
    )


_MANIFEST = """[package]
address = "github.com/pipelex-tests/folder-fix"
version = "1.0.0"
description = "A method whose tree is rooted above the folder a fix is handed"
"""


def _write_method_folder(*, directory: Path) -> tuple[Path, Path]:
    ideas_path = directory / "ideas.mthds"
    ideas_path.write_text(_IDEAS_MTHDS, encoding="utf-8")
    summary_path = directory / "summary.mthds"
    summary_path.write_text(_SUMMARY_MTHDS, encoding="utf-8")
    return ideas_path, summary_path


@pytest.mark.asyncio(loop_scope="class")
class TestFixMethodFolder:
    async def test_a_fix_lands_in_the_bundle_it_names_while_the_folder_is_judged_whole(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Two bundles each declaring a main pipe are no refusal: the whole folder is validated, and the fix lands where it points."""
        method_dir = tmp_path / "method"
        method_dir.mkdir()
        ideas_path, summary_path = _write_method_folder(directory=method_dir)
        validate_mock = mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=[_seq_output_error(source=str(ideas_path)), None],
        )

        result = await fix_method_folder(method_dir=method_dir, library_dirs=[method_dir], max_iterations=3)

        assert result.is_valid is True
        assert [fix.fix_code for fix in result.fixes_applied] == ["match-sequence-output"]
        assert [Path(written) for written in result.files_written] == [ideas_path.resolve()]
        fixed = tomlkit.loads(ideas_path.read_text(encoding="utf-8")).unwrap()
        assert fixed["pipe"]["list_ideas"]["output"] == "Idea[]"
        assert summary_path.read_text(encoding="utf-8") == _SUMMARY_MTHDS
        assert validate_mock.await_count == 2
        for call in validate_mock.await_args_list:
            assert {key: value for key, value in call.kwargs.items() if key != "tree_listing"} == {
                "method_dir": method_dir,
                "library_dirs": [method_dir],
                "library_dirs_are_callers": True,
                "allow_signatures": False,
            }
        # Each validation reads the listing its round's snapshot was taken from, and the round that wrote the fix
        # ended its listing, so the validation after it lists the trees anew.
        first_listing, second_listing = [call.kwargs["tree_listing"] for call in validate_mock.await_args_list]
        assert isinstance(first_listing, MethodTreeListing)
        assert isinstance(second_listing, MethodTreeListing)
        assert second_listing is not first_listing

    async def test_a_sourceless_fix_is_dropped_since_a_folder_has_no_entry_file(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """With no entry file, a fix that names no file has nowhere to land: nothing is written."""
        method_dir = tmp_path / "method"
        method_dir.mkdir()
        ideas_path, summary_path = _write_method_folder(directory=method_dir)
        mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=_seq_output_error(source=None),
        )

        result = await fix_method_folder(method_dir=method_dir, max_iterations=3)

        assert result.is_valid is False
        assert result.fixes_applied == []
        assert result.files_written == []
        assert [item.error_type for item in result.remaining_errors] == [PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT]
        assert ideas_path.read_text(encoding="utf-8") == _IDEAS_MTHDS
        assert summary_path.read_text(encoding="utf-8") == _SUMMARY_MTHDS

    async def test_a_fix_outside_the_write_scope_is_not_applied(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """``writable_library_dirs`` narrows the write scope: a fix aimed at a loaded file outside it touches nothing."""
        method_dir = tmp_path / "method"
        method_dir.mkdir()
        ideas_path, _ = _write_method_folder(directory=method_dir)
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=_seq_output_error(source=str(ideas_path)),
        )

        result = await fix_method_folder(method_dir=method_dir, writable_library_dirs=[elsewhere], max_iterations=3)

        assert result.is_valid is False
        assert result.fixes_applied == []
        assert result.files_written == []
        assert ideas_path.read_text(encoding="utf-8") == _IDEAS_MTHDS

    async def test_a_fix_of_a_subfolder_lands_in_a_sibling_bundle_of_its_tree(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """The tree is rooted at the `METHODS.toml` above the folder handed over, and a fix may write any bundle of it."""
        root_dir = tmp_path / "method"
        sub_dir = root_dir / "sub"
        sub_dir.mkdir(parents=True)
        (root_dir / "METHODS.toml").write_text(_MANIFEST, encoding="utf-8")
        ideas_path = root_dir / "ideas.mthds"
        ideas_path.write_text(_IDEAS_MTHDS, encoding="utf-8")
        summary_path = sub_dir / "summary.mthds"
        summary_path.write_text(_SUMMARY_MTHDS, encoding="utf-8")
        mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            # A file of the tree outside the folder loaded is named by its absolute location, as the load names it.
            side_effect=[_seq_output_error(source=str(ideas_path.resolve())), None],
        )

        result = await fix_method_folder(method_dir=sub_dir, library_dirs=[sub_dir], max_iterations=3)

        assert result.is_valid is True
        assert result.bail_reason is None
        assert [Path(written) for written in result.files_written] == [ideas_path.resolve()]
        fixed = tomlkit.loads(ideas_path.read_text(encoding="utf-8")).unwrap()
        assert fixed["pipe"]["list_ideas"]["output"] == "Idea[]"
        assert summary_path.read_text(encoding="utf-8") == _SUMMARY_MTHDS

    async def test_a_library_directory_naming_the_folder_otherwise_is_not_loaded_twice(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """The folder is left out of the directories beside it however it is spelled, compared resolved."""
        method_dir = tmp_path / "method"
        method_dir.mkdir()
        _write_method_folder(directory=method_dir)
        linked_dir = tmp_path / "linked"
        linked_dir.symlink_to(method_dir, target_is_directory=True)
        snapshot_spy = mocker.spy(fix_loop, "_snapshot_loaded_sources")
        mocker.patch("pipelex.pipeline.fixes.fix_loop.validate_bundle", return_value=None)

        result = await fix_method_folder(method_dir=method_dir, library_dirs=[linked_dir, method_dir], max_iterations=3)

        assert result.is_valid is True
        assert snapshot_spy.call_args.kwargs["effective_dirs"] == [method_dir]
