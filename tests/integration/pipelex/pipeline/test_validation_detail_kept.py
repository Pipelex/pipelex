"""Pin: every validation error reaches the reader, with the locators the raise site had.

Validation used to lose detail before the verdict was built. These tests load real bundles through
``validate_bundle`` and pin what the verdict now keeps:

- **Every error is an item.** A misspelled field (pydantic's ``extra_forbidden``, which no categorizer
  knows) beside an undeclared prompt variable gives two items, the typo as an uncategorized
  ``blueprint_validation`` item carrying its source, its pipe and its field path.
- **One located item per failing dry-run pipe.** A ``PipeParallel`` whose plural branch feeds a single
  field fails its combine; nested in a ``PipeSequence``, the failure used to reach the reader as one
  item holding a Python repr of the sweep's records, once for each level of nesting. It is now one
  ``dry_run`` item for the innermost failing pipe, carrying its code, domain and source, whose text
  follows the disclosure rule: the failure's own message only when it is caller-facing.
- **The positions the parser knew.** A TOML syntax error's item carries its 1-based line and column, and
  an unresolved concept's item lists the concepts its domain declares.
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.core.stuffs.exceptions import StuffFactoryError
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.validation_error_types import PipeValidationErrorType
from tests.integration.pipelex.test_data import ValidationDetailBundles


async def _validation_items(*, bundle: str, dry_run_pipe_codes: list[str] | None = None) -> list[ValidationErrorItem]:
    with pytest.raises(ValidateBundleError) as exc_info:
        await validate_bundle(mthds_contents=[bundle], mthds_sources=[ValidationDetailBundles.SOURCE], dry_run_pipe_codes=dry_run_pipe_codes)
    return list(exc_info.value.to_error_report().validation_errors or [])


class TestValidationDetailKept:
    @pytest.mark.asyncio
    async def test_an_uncategorized_error_is_kept_beside_a_categorized_one(self) -> None:
        items = await _validation_items(bundle=ValidationDetailBundles.TYPO_BESIDE_UNDECLARED_VARIABLE)

        assert len(items) == 2
        typo_item = next(item for item in items if item.error_type is None)
        assert typo_item.category == ValidationErrorCategory.BLUEPRINT_VALIDATION
        assert typo_item.pipe_code == "summarize_notes"
        assert typo_item.domain_code == ValidationDetailBundles.DOMAIN
        assert typo_item.source == ValidationDetailBundles.SOURCE
        assert typo_item.field_path == "pipe.summarize_notes.promtp"
        assert typo_item.message == "Validation error at 'pipe.summarize_notes.promtp': Extra inputs are not permitted"

        variable_item = next(item for item in items if item.error_type is not None)
        assert variable_item.error_type == PipeValidationErrorType.MISSING_INPUT_VARIABLE
        assert variable_item.pipe_code == "translate_notes"
        assert variable_item.variable_names == ["language"]

    @pytest.mark.asyncio
    async def test_a_nested_dry_run_failure_is_one_item_at_the_innermost_pipe(self, mocker: MockerFixture) -> None:
        # The combine's StuffFactoryError is flagged caller-facing here, as a caller's own method fault is
        # classified at its raise site, so the item carries the combine's own message.
        mocker.patch.object(StuffFactoryError, "_authors_caller_facing_message", new=True)

        items = await _validation_items(bundle=ValidationDetailBundles.NESTED_PARALLEL_MISMATCH)

        (item,) = items
        assert item.category == ValidationErrorCategory.DRY_RUN
        assert item.error_type == "DryRunError"
        assert item.pipe_code == "analyze_topic"
        assert item.domain_code == ValidationDetailBundles.DOMAIN
        assert item.source == ValidationDetailBundles.SOURCE
        assert item.message.startswith("Pipe 'analyze_topic' failed its dry run: Error combining stuffs for concept IdeaReport")
        assert "expected idea_board__Idea, got ListContent" in item.message
        assert not any(marker in item.message for marker in ValidationDetailBundles.RECORD_REPR_MARKERS)

    @pytest.mark.asyncio
    async def test_a_dry_run_failure_that_is_not_caller_facing_names_its_title(self) -> None:
        items = await _validation_items(bundle=ValidationDetailBundles.NESTED_PARALLEL_MISMATCH)

        (item,) = items
        assert item.pipe_code == "analyze_topic"
        assert item.message == f"Pipe 'analyze_topic' failed its dry run: {StuffFactoryError.title()}"

    @pytest.mark.asyncio
    async def test_the_enclosing_pipe_alone_reports_the_innermost_failing_pipe(self) -> None:
        # Only the sequence is dry-run, and its failure is reported where it happened: at the parallel.
        items = await _validation_items(bundle=ValidationDetailBundles.NESTED_PARALLEL_MISMATCH, dry_run_pipe_codes=["run_workshop"])

        (item,) = items
        assert item.category == ValidationErrorCategory.DRY_RUN
        assert item.pipe_code == "analyze_topic"
        assert item.domain_code == ValidationDetailBundles.DOMAIN

    @pytest.mark.asyncio
    async def test_a_toml_syntax_error_carries_its_line_and_column(self) -> None:
        (item,) = await _validation_items(bundle=ValidationDetailBundles.TOML_SYNTAX_ERROR)

        assert item.category == ValidationErrorCategory.BLUEPRINT_VALIDATION
        assert item.error_type is None
        assert item.source == ValidationDetailBundles.SOURCE
        assert item.line == 2
        assert item.column == 38

    @pytest.mark.asyncio
    async def test_an_unresolved_concept_lists_the_concepts_its_domain_declares(self) -> None:
        (item,) = await _validation_items(bundle=ValidationDetailBundles.UNRESOLVED_CONCEPT)

        assert item.error_type == PipeValidationErrorType.UNRESOLVED_CONCEPT
        assert item.concept_code == "IdeaRanking"
        assert item.declared_concepts == ["Idea", "IdeaSummary"]

    @pytest.mark.asyncio
    async def test_a_failure_in_a_library_pipe_never_names_the_host_file(self, tmp_path: Path) -> None:
        """A pipe loaded from the host's library directories is located, but its file on the host stays out of the verdict."""
        library_dir = tmp_path / "host_library"
        library_dir.mkdir()
        (library_dir / "idea_board.mthds").write_text(ValidationDetailBundles.NESTED_PARALLEL_MISMATCH, encoding="utf-8")

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(
                mthds_contents=[ValidationDetailBundles.CALLER_OF_LIBRARY_PARALLEL],
                mthds_sources=[ValidationDetailBundles.CALLER_SOURCE],
                library_dirs=[library_dir],
            )

        (item,) = exc_info.value.to_error_report().validation_errors or []
        assert item.category == ValidationErrorCategory.DRY_RUN
        assert (item.pipe_code, item.domain_code) == ("analyze_topic", ValidationDetailBundles.DOMAIN)
        assert item.source is None
        assert str(tmp_path) not in item.message

    @pytest.mark.asyncio
    async def test_a_failure_in_a_sibling_file_of_a_local_method_names_that_file(self, tmp_path: Path) -> None:
        """Validated from a file on the caller's own disk, a failure in a sibling file of the method keeps that file."""
        method_dir = tmp_path / "method"
        method_dir.mkdir()
        entry_file = method_dir / "main.mthds"
        entry_file.write_text(ValidationDetailBundles.CALLER_OF_LIBRARY_PARALLEL, encoding="utf-8")
        sibling_file = method_dir / "idea_board.mthds"
        sibling_file.write_text(ValidationDetailBundles.NESTED_PARALLEL_MISMATCH, encoding="utf-8")

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_file_path=entry_file, library_dirs=[method_dir])

        (item,) = exc_info.value.to_error_report().validation_errors or []
        assert (item.pipe_code, item.domain_code) == ("analyze_topic", ValidationDetailBundles.DOMAIN)
        assert item.source is not None
        assert Path(item.source).resolve() == sibling_file.resolve()
