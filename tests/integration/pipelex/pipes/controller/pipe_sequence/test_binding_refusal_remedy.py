import re

import pytest

from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipe_controllers.binding.binding_step_blueprint import BindingStepBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
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
