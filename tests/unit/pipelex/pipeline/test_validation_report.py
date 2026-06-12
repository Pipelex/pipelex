"""Pin the D14 assembly contract of ``build_validation_report``.

The canonical ``PipelexValidationReport`` is constructed in exactly one place — this assembly
function — by every backend (local protocol ``validate``, hosted direct, hosted Temporal). The
test pins what the assembly derives from its ingredients: primary-blueprint selection for
``bundle_blueprint`` (first declaring ``main_pipe``, else first), the ``validated_pipes``
projection from the dry-run status map, and ``is_runnable = not pending_signatures``.

Pure unit test (no Pipelex boot): blueprints from the interpreter, hand-built status map.
"""

from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.pipeline.bundle_validator import DryRunOutput, DryRunStatus
from pipelex.pipeline.pipe_structures import IOMultiplicity, PipeIOContract, PipeOutputContract
from pipelex.pipeline.validation_report import build_validation_report

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
            PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=_NO_MAIN_PIPE_MTHDS),
            PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=_MAIN_PIPE_MTHDS),
        ]
        pipe_structures = {
            "beta.do_it": PipeIOContract(
                inputs={},
                output=PipeOutputContract(concept_code="native.Text", multiplicity=IOMultiplicity.SINGLE),
            ),
        }
        dry_run_result: dict[str, DryRunOutput] = {
            "beta.do_it": DryRunOutput(pipe_code="do_it", pipe_ref="beta.do_it", status=DryRunStatus.SUCCESS),
        }

        report = build_validation_report(
            blueprints=blueprints,
            pipe_structures=pipe_structures,
            dry_run_result=dry_run_result,
            pending_signatures=["beta.still_pending"],
        )

        # Primary selection: the first blueprint declaring main_pipe wins, not the first in the batch.
        assert report.bundle_blueprint is blueprints[1]
        assert report.pipe_structures == pipe_structures
        assert report.validated_pipes == [{"pipe_ref": "beta.do_it", "status": DryRunStatus.SUCCESS}]
        assert report.pending_signatures == ["beta.still_pending"]
        assert report.is_runnable is False
        assert report.graph_spec is None

    def test_runnable_when_nothing_pending(self) -> None:
        blueprints = [PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=_MAIN_PIPE_MTHDS)]

        report = build_validation_report(
            blueprints=blueprints,
            pipe_structures={},
            dry_run_result={},
            pending_signatures=[],
        )

        assert report.bundle_blueprint is blueprints[0]
        assert report.is_runnable is True
        assert report.validated_pipes == []
