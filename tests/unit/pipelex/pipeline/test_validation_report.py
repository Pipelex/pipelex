"""Pin the D14 assembly contract of ``build_validation_report``.

The canonical ``PipelexValidationReport`` is constructed in exactly one place — this assembly
function — by every backend (local protocol ``validate``, hosted direct, hosted Temporal). The
test pins what the assembly derives from its ingredients: primary-blueprint selection for
``bundle_blueprint`` (first declaring ``main_pipe``, else first), the ``validated_pipes``
projection from the dry-run status map, the per-file ``tree_file_readers`` view derived from
``tree_files_read``, and ``is_runnable = not pending_signatures``.

Pure unit test (no Pipelex boot): blueprints from the interpreter, hand-built status map.
"""

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.core.method_trees.tree_file_reads import TreeFileRead, TreeFileUse
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipeline.bundle_validator import DryRunOutput, DryRunStatus
from pipelex.pipeline.pipe_io_contracts import IOMultiplicity, PipeIOContract, PipeOutputContract
from pipelex.pipeline.validation_report import build_validation_report
from pipelex.validation_error_types import PipeValidationErrorType

_NO_MAIN_PIPE_MTHDS = """
domain = "alpha"
description = "Concepts only, no main_pipe"

[concept.Thing]
description = "A thing"
"""

_MAIN_PIPE_MTHDS = """
domain = "beta"
description = "Declares a main_pipe"
main_pipe = "do_it"

[pipe.do_it]
type = "PipeLLM"
description = "Do it"
inputs = { doc = "Text" }
output = "Text"
prompt = "Do it with $doc"
"""


class TestBuildValidationReport:
    def test_assembles_canonical_report_from_ingredients(self) -> None:
        blueprints = [
            MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_NO_MAIN_PIPE_MTHDS),
            MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_MAIN_PIPE_MTHDS),
        ]
        pipe_io_contracts = {
            "beta.do_it": PipeIOContract(
                inputs={},
                output=PipeOutputContract(
                    concept_ref="native.Text",
                    multiplicity=IOMultiplicity.SINGLE,
                    item_count=None,
                    optional=False,
                    # The payload's schema: `native.Text` resolves to its content model, which
                    # wraps the value under `text`.
                    json_schema={"type": "object", "properties": {"text": {"type": "string"}}},
                ),
            ),
        }
        dry_run_result: dict[str, DryRunOutput] = {
            "beta.do_it": DryRunOutput(pipe_code="do_it", pipe_ref="beta.do_it", status=DryRunStatus.SUCCESS),
        }

        report = build_validation_report(
            blueprints=blueprints,
            pipe_io_contracts=pipe_io_contracts,
            input_form={},
            output_form={},
            dry_run_result=dry_run_result,
            pending_signatures=["beta.still_pending"],
            tree_files_read={"beta.do_it": []},
        )

        # is_valid is the always-True discriminant of the valid arm of the HTTP response union.
        assert report.is_valid is True
        # Primary selection: the first blueprint declaring main_pipe wins, not the first in the batch.
        assert report.bundle_blueprint is blueprints[1]
        assert report.pipe_io_contracts == pipe_io_contracts
        assert report.validated_pipes == [{"pipe_ref": "beta.do_it", "status": DryRunStatus.SUCCESS}]
        assert report.pending_signatures == ["beta.still_pending"]
        assert report.is_runnable is False
        assert report.graph_spec is None
        assert report.tree_files_read == {"beta.do_it": []}
        assert report.tree_file_readers == {}

    def test_runnable_when_nothing_pending(self) -> None:
        blueprints = [MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_MAIN_PIPE_MTHDS)]

        report = build_validation_report(
            blueprints=blueprints,
            pipe_io_contracts={},
            input_form={},
            output_form={},
            dry_run_result={},
            pending_signatures=[],
            tree_files_read={},
        )

        assert report.bundle_blueprint is blueprints[0]
        assert report.is_runnable is True
        assert report.validated_pipes == []
        # The advisory channel defaults empty and never affects the verdict.
        assert report.warnings == []

    def test_warnings_ride_the_report_without_flipping_the_verdict(self) -> None:
        """Warnings share the error item shape but the report stays the valid arm (is_valid True)."""
        blueprints = [MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_MAIN_PIPE_MTHDS)]
        warning_item = ValidationErrorItem(
            category=ValidationErrorCategory.PIPE_VALIDATION,
            error_type=PipeValidationErrorType.OPTIONAL_FORCE_REDUNDANT,
            pipe_code="do_it",
            domain_code="beta",
            variable_names=["doc"],
            message="Input 'doc' of pipe 'beta.do_it' is declared '!' but is guaranteed present in every analyzed flow.",
        )

        report = build_validation_report(
            blueprints=blueprints,
            pipe_io_contracts={},
            input_form={},
            output_form={},
            dry_run_result={},
            pending_signatures=[],
            tree_files_read={},
            warnings=[warning_item],
        )

        assert report.is_valid is True
        assert report.warnings == [warning_item]

    def test_the_per_file_view_is_derived_from_the_files_each_pipe_reads(self) -> None:
        """Each tree path a pipe reads, sorted, names every pipe reading it once, in the order the per-pipe view lists them."""
        blueprints = [MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_MAIN_PIPE_MTHDS)]
        letterhead = TreeFileRead(tree_path="templates/letterhead.html", use=TreeFileUse.TEMPLATE)
        logo = TreeFileRead(tree_path="templates/logo.png", use=TreeFileUse.TEMPLATE_ASSET)
        totals_module = TreeFileRead(tree_path="funcs/totals.py", use=TreeFileUse.PYTHON_MODULE)
        tree_files_read = {
            "beta.write_letter": [letterhead, logo],
            "beta.write_reminder": [letterhead, logo],
            "beta.compute_totals": [totals_module],
            "beta.do_it": [],
        }

        report = build_validation_report(
            blueprints=blueprints,
            pipe_io_contracts={},
            input_form={},
            output_form={},
            dry_run_result={},
            pending_signatures=[],
            tree_files_read=tree_files_read,
        )

        assert report.tree_files_read == tree_files_read
        assert report.tree_file_readers == {
            "funcs/totals.py": ["beta.compute_totals"],
            "templates/letterhead.html": ["beta.write_letter", "beta.write_reminder"],
            "templates/logo.png": ["beta.write_letter", "beta.write_reminder"],
        }
        assert list(report.tree_file_readers) == sorted(report.tree_file_readers)
        assert report.model_dump(mode="json")["tree_files_read"]["beta.compute_totals"] == [{"tree_path": "funcs/totals.py", "use": "python_module"}]
