"""A PipeDocGen template the template sandbox refuses is located on the field the bundle writes it in."""

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.errors.problem import ProblemView
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.test_data import PipeDocGenTestData

# A template that reads a private name its own source spells, which the sandbox refuses whatever the run's data.
_REFUSED_TEMPLATE = "<p>{{ invoice['_owner'] }}</p>"


@pytest.mark.asyncio(loop_scope="class")
@pytest.mark.usefixtures("stub_engines")
class TestPipeDocGenTemplateRefusalLocation:
    @pytest.mark.parametrize(
        ("step_fields", "submitted_files", "expected_field"),
        [
            pytest.param(f'format = "pdf"\nfilename = "{_REFUSED_TEMPLATE}"', None, "filename", id="filename"),
            pytest.param(f'format = "pdf"\ntemplate = "{_REFUSED_TEMPLATE}"', None, "template", id="inline_template"),
            pytest.param(
                'format = "pdf"\ntemplate_file = "templates/invoice.html"',
                {"./templates/invoice.html": _REFUSED_TEMPLATE.encode()},
                "template_file",
                id="template_file",
            ),
        ],
    )
    async def test_a_refused_template_is_located_on_its_field(
        self, step_fields: str, submitted_files: dict[str, bytes] | None, expected_field: str
    ) -> None:
        with pytest.raises(PipelexError) as exc_info:
            await PipelexMTHDSProtocol(submitted_files=submitted_files).execute(
                mthds_contents=[PipeDocGenTestData.bundle(step_fields=step_fields)], inputs=PipeDocGenTestData.INVOICE_INPUTS
            )

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)

        assert caller.code == CoreCode.SECURITY_TEMPLATE_REFUSED, caller.to_wire()
        assert caller.params is not None
        assert caller.params.as_wire() == {"pipe": "print_invoice", "name": "_owner"}
        assert caller.location is not None
        assert caller.location.as_wire() == {"pipe": "print_invoice", "path": ["print_invoice"], "field": expected_field}
