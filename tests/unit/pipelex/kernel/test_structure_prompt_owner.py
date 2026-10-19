"""The structure prompt is Pipelex's own template, so a failure to render it is ours, not the method's.

The template is config-editable: an edit naming a filter the environment lacks must report
`runtime.unexpected`, never the method's `method.template_invalid`, since no method wrote it.
"""

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.cogt.config_cogt import LLMConfig
from pipelex.kernel.llm_ops import derive_structure_prompt
from pipelex.test_extras.registry_test_models import FictionCharacter
from pipelex.tools.jinja2.exceptions import Jinja2TemplateInvalidError
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat

_TEMPLATING_STYLE = TemplatingStyle(tag_style=TagStyle.NO_TAG, text_format=TextFormat.PLAIN)

#: An edited structure-prompt template naming a filter the environment lacks.
_EDITED_TEMPLATE_WITH_AN_UNKNOWN_FILTER = "{{ class_structure_str | frob_the_structure }}"


class TestStructurePromptOwner:
    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_broken_structure_prompt_template_is_ours(self, mocker: MockerFixture) -> None:
        mocker.patch.object(LLMConfig, "get_template", return_value=_EDITED_TEMPLATE_WITH_AN_UNKNOWN_FILTER)

        with pytest.raises(Jinja2TemplateInvalidError) as exc_info:
            await derive_structure_prompt(output_class=FictionCharacter, templating_style=_TEMPLATING_STYLE)

        assert exc_info.value.to_error_report().code == CoreCode.RUNTIME_UNEXPECTED
