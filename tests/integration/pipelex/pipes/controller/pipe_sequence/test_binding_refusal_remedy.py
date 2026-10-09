import re

import pytest

from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipe_controllers.binding.binding_step_blueprint import BindingStepBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.validation_error_types import PipeValidationErrorType

_IMAGE_URL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGM4IScHAAK2AQU0pnWqAAAAAElFTkSuQmCC"

_REFUSED_BUNDLE = """domain = "catalog_views"
description = "Describing the photograph of a catalog page"
main_pipe = "describe_view"

[pipe.describe_view]
type = "PipeCompose"
description = "Describes the photograph of a catalog page"
inputs = { "page.page_view" = "Image" }
output = "Text"
template = "View: {{ page.page_view.caption }}"
"""

_REMEDIED_BUNDLE_TEMPLATE = """domain = "catalog_views"
description = "Describing the photograph of a catalog page"
main_pipe = "describe_page"

[pipe.describe_page]
type = "PipeSequence"
description = "Binds the view of a page, then describes it"
inputs = {{ page = "Page" }}
output = "Text?"
steps = [
  {binding_step},
  {{ pipe = "describe_view", result = "description" }},
]

[pipe.describe_view]
type = "PipeCompose"
description = "Describes the photograph of a catalog page"
inputs = {{ page_view = "Image" }}
output = "Text"
template = "View: {{{{ page_view.caption }}}}"
"""

# A root that is not a plain name: no input can bear it, and no step can store a value under it either, since a pipe step's
# `result` is a stored name, held to the plain input-name form like an input name.
_UPPERCASE_ROOT_BUNDLE = """domain = "billing"
description = "Reading the total of an invoice stored under a name that is not a plain name"
main_pipe = "read_total"

[concept.Invoice]
description = "An invoice sent by a supplier"

[concept.Invoice.structure]
total = { type = "number", description = "The amount due", required = true }

[pipe.make_invoice]
type = "PipeCompose"
description = "Writes out an invoice for an amount"
inputs = { amount = "Number" }
output = "Invoice"

[pipe.make_invoice.construct]
total = { from = "amount.number" }

[pipe.read_total]
type = "PipeSequence"
description = "Writes out an invoice, then binds its total"
inputs = { amount = "Number" }
output = "Number"
steps = [
  { pipe = "make_invoice", result = "Invoice" },
  { from = "Invoice.total", result = "total" },
]
"""


class TestBindingRefusalRemedy:
    @pytest.mark.asyncio(loop_scope="class")
    async def test_the_binding_step_a_refusal_prints_parses_validates_and_runs(self) -> None:
        """The binding step the dotted-input refusal prints, pasted as it stands into a calling sequence, is a working step."""
        with pytest.raises(MthdsParserError) as exc_info:
            MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_REFUSED_BUNDLE, mthds_source="refused.mthds")
        errors = exc_info.value.validation_errors
        assert [error.error_type for error in errors] == [PipeValidationErrorType.INVALID_INPUT_NAME]
        printed_steps = re.findall(r"`(\{ from = [^`]*\})`", errors[0].message)
        assert printed_steps == ['{ from = "page.page_view", result = "page_view" }']

        remedied_bundle = _REMEDIED_BUNDLE_TEMPLATE.format(binding_step=printed_steps[0])
        blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=remedied_bundle, mthds_source="remedied.mthds")
        assert blueprint.pipe is not None
        sequence_blueprint = blueprint.pipe["describe_page"]
        assert isinstance(sequence_blueprint, PipeSequenceBlueprint)
        assert sequence_blueprint.steps[0] == BindingStepBlueprint.model_validate({"from": "page.page_view", "result": "page_view"})

        validation = await validate_bundle(mthds_contents=[remedied_bundle])
        assert validation.blueprints

        result = await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.LIVE).execute(
            mthds_contents=[remedied_bundle],
            inputs={
                "page": {
                    "concept": "native.Page",
                    "content": {
                        "text_and_images": {"text": {"text": "Garden chairs"}},
                        "page_view": {"url": _IMAGE_URL, "caption": "Garden chairs on a lawn"},
                    },
                }
            },
        )
        assert result.pipe_output.main_stuff.as_text.text == "View: Garden chairs on a lawn"

    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_pipe_step_storing_under_a_name_that_is_not_plain_is_refused(self) -> None:
        """A pipe step's `result` is a stored name, so it cannot store the value a root that is not a plain name would read."""
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[_UPPERCASE_ROOT_BUNDLE])

        validation_errors = exc_info.value.to_error_report().validation_errors or []
        assert [error.error_type for error in validation_errors] == [PipeValidationErrorType.INVALID_INPUT_NAME]
        assert validation_errors[0].variable_names == ["Invoice"]
        message = validation_errors[0].message or ""
        assert "The `result` of the step running pipe 'make_invoice', 'Invoice', is not a plain input name" in message
        assert "Rename it to a plain name, such as 'invoice'," in message

    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_missing_root_that_is_not_a_plain_name_is_never_asked_for_as_an_input(self) -> None:
        """Regression: the refusal of a root nothing stores never asks to declare it, or to store a value under it, when it is not plain."""
        mthds_content = _UPPERCASE_ROOT_BUNDLE.replace('  { pipe = "make_invoice", result = "Invoice" },\n', "")

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[mthds_content])

        validation_errors = exc_info.value.to_error_report().validation_errors or []
        assert [error.error_type for error in validation_errors] == [PipeValidationErrorType.MISSING_INPUT_VARIABLE]
        message = validation_errors[0].message or ""
        assert "Declare 'Invoice'" not in message
        assert "store a value under 'Invoice'" not in message
        assert "it can be neither an input of the sequence nor a name a step stores a value under" in message
        assert "bind from a plain name, such as 'invoice'," in message
