import inspect
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.core.exceptions import (
    DryRunFailureErrorData,
    PipeFactoryErrorData,
    PipelexBundleBlueprintValidationErrorData,
    PipesAndConceptValidationErrorData,
)
from pipelex.pipeline import validate_bundle_translation
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle_translation import HOST_LIBRARY_FILE_PLACEHOLDER, withholding_host_library_files
from pipelex.validation_error_types import PipeFactoryErrorType

_HOST_FILE = "/srv/pipelex/host-library/harbour_board.mthds"

# Every channel ``ValidateBundleError`` takes. ``withholding_files`` rebuilds the verdict channel by channel, so a
# channel added to the constructor and not carried there would be silently dropped from every withheld verdict.
_CHANNELS = {
    "message",
    "pipelex_bundle_blueprint_validation_errors",
    "pipe_factory_errors",
    "pipe_validation_errors",
    "pipe_concept_instantiation_errors",
    "dry_run_failures",
}


def _mentioning_the_host_file(*, label: str) -> str:
    return f"{label} in '{_HOST_FILE}'"


class TestValidateBundleErrorWithholding:
    def test_every_channel_of_the_verdict_is_carried(self) -> None:
        constructor_channels = set(inspect.signature(ValidateBundleError.__init__).parameters) - {"self"}
        assert constructor_channels == _CHANNELS, "a channel added to ValidateBundleError must be carried by withholding_files too"

    def test_every_channel_names_no_withheld_file(self) -> None:
        verdict = ValidateBundleError(
            message=_mentioning_the_host_file(label="raw"),
            pipelex_bundle_blueprint_validation_errors=[
                PipelexBundleBlueprintValidationErrorData(message=_mentioning_the_host_file(label="blueprint"), source=_HOST_FILE)
            ],
            pipe_factory_errors=[
                PipeFactoryErrorData(error_type=PipeFactoryErrorType.UNKNOWN_FACTORY_ERROR, message=_mentioning_the_host_file(label="factory"))
            ],
            pipe_validation_errors=[
                # Located from the pipe-source map, a pipe-validation error carries its file as its field path too.
                PipesAndConceptValidationErrorData(message=_mentioning_the_host_file(label="pipe"), source=_HOST_FILE, field_path=_HOST_FILE)
            ],
            pipe_concept_instantiation_errors=[
                PipesAndConceptValidationErrorData(
                    message=_mentioning_the_host_file(label="instantiation"), source="api://bundle-0.mthds", field_path=""
                )
            ],
            dry_run_failures=[DryRunFailureErrorData(pipe_code="post_notice", message=_mentioning_the_host_file(label="dry run"), source=_HOST_FILE)],
        )

        withheld = verdict.withholding_files(withheld_files={_HOST_FILE}, placeholder=HOST_LIBRARY_FILE_PLACEHOLDER)

        items = withheld.to_error_report().validation_errors or []
        assert [item.message for item in items] == [
            f"blueprint in '{HOST_LIBRARY_FILE_PLACEHOLDER}'",
            f"factory in '{HOST_LIBRARY_FILE_PLACEHOLDER}'",
            f"pipe in '{HOST_LIBRARY_FILE_PLACEHOLDER}'",
            f"instantiation in '{HOST_LIBRARY_FILE_PLACEHOLDER}'",
            f"dry run in '{HOST_LIBRARY_FILE_PLACEHOLDER}'",
        ]
        # A withheld file's source is dropped; any other source is the same answer as before.
        assert [item.source for item in items] == [None, None, None, "api://bundle-0.mthds", None]
        assert [item.field_path for item in items] == [None, None, None, None, None]
        assert _HOST_FILE not in withheld.message

    def test_a_withheld_name_counts_only_standing_on_its_own(self) -> None:
        # A host library directory listed relatively names its files relatively, so a host file's name can be the
        # tail of the caller's own names, which are left alone.
        verdict = ValidateBundleError(message="Could not load 'harbour_board.mthds' beside 'api://harbour_board.mthds' and 'old_harbour_board.mthds'")

        withheld = verdict.withholding_files(withheld_files={"harbour_board.mthds"}, placeholder=HOST_LIBRARY_FILE_PLACEHOLDER)

        assert (
            withheld.message == f"Could not load '{HOST_LIBRARY_FILE_PLACEHOLDER}' beside 'api://harbour_board.mthds' and 'old_harbour_board.mthds'"
        )

    def test_nothing_to_withhold_leaves_the_verdict_as_it_reads(self) -> None:
        verdict = ValidateBundleError(message="Pipe 'post_notice' could not be loaded")

        withheld = verdict.withholding_files(withheld_files=set(), placeholder=HOST_LIBRARY_FILE_PLACEHOLDER)

        assert withheld.message == "Pipe 'post_notice' could not be loaded"

    def test_a_callers_source_spelled_like_a_host_file_is_kept(self, tmp_path: Path) -> None:
        host_library_file = tmp_path / "harbour_board.mthds"
        host_library_file.write_text('domain = "harbour_board"\ndescription = "Notices of the harbour board"\n', encoding="utf-8")
        callers_source = str(host_library_file)
        verdict = ValidateBundleError(
            message="Pipe 'post_notice' could not be loaded",
            pipe_validation_errors=[
                PipesAndConceptValidationErrorData(message="Pipe 'post_notice' could not be loaded", source=callers_source, field_path="")
            ],
        )

        with pytest.raises(ValidateBundleError) as raised, withholding_host_library_files(library_dirs=[tmp_path], caller_sources=[callers_source]):
            raise verdict

        (item,) = raised.value.to_error_report().validation_errors or []
        assert item.source == callers_source

    def test_the_host_s_files_and_the_template_files_its_steps_name_are_found_in_one_walk(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """The host's directories are listed once, and each bundle file read once, for both its name and its steps' template files."""
        host_library_file = tmp_path / "harbour_board.mthds"
        host_library_file.write_text(
            'domain = "harbour_board"\n\n[pipe.print_notice]\ntype = "PipeDocGen"\nformat = "docx"\ntemplate_file = "notice-template.docx"\n',
            encoding="utf-8",
        )
        message = f"Pipe 'print_notice' in '{host_library_file}' could not read 'notice-template.docx'"
        walk_spy = mocker.spy(validate_bundle_translation, "get_pipelex_mthds_files_from_dirs")

        with pytest.raises(ValidateBundleError) as raised, withholding_host_library_files(library_dirs=[tmp_path]):
            raise ValidateBundleError(message=message)

        assert raised.value.message == f"Pipe 'print_notice' in '{HOST_LIBRARY_FILE_PLACEHOLDER}' could not read '{HOST_LIBRARY_FILE_PLACEHOLDER}'"
        assert walk_spy.call_count == 1

    def test_a_host_tree_that_cannot_be_listed_while_withholding_never_replaces_the_verdict(self, tmp_path: Path) -> None:
        """The host's files are still withheld, from every bundle file under its directories, and the verdict stays the verdict."""
        host_library_file = tmp_path / "harbour_board.mthds"
        host_library_file.write_text('domain = "harbour_board"\n', encoding="utf-8")
        hidden_host_file = tmp_path / ".drafts" / "tide_board.mthds"
        hidden_host_file.parent.mkdir()
        hidden_host_file.write_text('domain = "tide_board"\n', encoding="utf-8")
        # A symbolic link is refused by the membership rule, so listing the host's tree fails.
        (tmp_path / "linked.mthds").symlink_to(host_library_file)
        message = f"Pipe 'post_notice' in '{host_library_file}' could not be loaded, nor '{hidden_host_file}'"

        with pytest.raises(ValidateBundleError) as raised, withholding_host_library_files(library_dirs=[tmp_path]):
            raise ValidateBundleError(message=message)

        assert raised.value.message == (
            f"Pipe 'post_notice' in '{HOST_LIBRARY_FILE_PLACEHOLDER}' could not be loaded, nor '{HOST_LIBRARY_FILE_PLACEHOLDER}'"
        )
