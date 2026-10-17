from __future__ import annotations

import json
from typing import Any

import pytest

from pipelex.errors.problem import ProblemView
from pipelex.system.exceptions import ToolError
from pipelex.tools.jinja2.exceptions import Jinja2TemplateInvalidError, Jinja2TemplateRenderError, Jinja2TemplateSecurityError
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async, render_jinja2_sync
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.jinja2.template_owner import TemplateOwner

# A value of the run's data, which no message, parameter or diagnostic carries.
_PAYLOAD = "confidential-patient-diagnosis"


async def _render_failure(*, template_source: str, context: dict[str, Any], is_async: bool) -> ToolError:
    """The error rendering `template_source` raises, through the synchronous or the asynchronous render."""
    if is_async:
        with pytest.raises(ToolError) as async_exc_info:
            await render_jinja2_async(
                template_source=template_source,
                template_category=TemplateCategory.BASIC,
                templating_context=context,
                template_owner=TemplateOwner.METHOD,
            )
        return async_exc_info.value
    with pytest.raises(ToolError) as sync_exc_info:
        render_jinja2_sync(
            template_source=template_source,
            template_category=TemplateCategory.BASIC,
            templating_context=context,
            template_owner=TemplateOwner.METHOD,
        )
    return sync_exc_info.value


@pytest.mark.asyncio(loop_scope="class")
class TestJinja2RenderFailureText:
    @pytest.mark.parametrize("is_async", [False, True], ids=["sync", "async"])
    @pytest.mark.parametrize(
        ("topic", "template_source", "context", "expected_error", "expected_message"),
        [
            (
                "a key of the data a lookup did not find",
                "Notes:\n{{ mapping[lookup].field }}",
                {"mapping": {}, "lookup": _PAYLOAD},
                Jinja2TemplateRenderError,
                "Jinja2 render — undefined error: the template reads a value that is not defined (UndefinedError, at line 2 of the template)",
            ),
            (
                "a template that includes the template a value names",
                "{% include lookup %}",
                {"lookup": _PAYLOAD},
                Jinja2TemplateInvalidError,
                (
                    "Jinja2 render — the template cannot render as written: "
                    "template not found: the template includes, imports or extends a template it cannot reach."
                ),
            ),
            (
                "a private name read by a key of the data",
                "{{ record[lookup] }}",
                {"record": object(), "lookup": f"_{_PAYLOAD.replace('-', '_')}"},
                Jinja2TemplateSecurityError,
                "Jinja2 render — refused by the template sandbox: A template may not read an unsafe name on a 'object' value.",
            ),
            (
                "an operation on a value of the wrong type",
                "{{ count + lookup }}",
                {"count": 1, "lookup": _PAYLOAD},
                Jinja2TemplateRenderError,
                (
                    "Jinja2 render — type error: the template applied an operation to a value of a type that does not support it "
                    "(TypeError, at line 1 of the template)"
                ),
            ),
        ],
    )
    async def test_a_failure_on_the_run_s_data_quotes_none_of_it(
        self,
        topic: str,
        template_source: str,
        context: dict[str, Any],
        expected_error: type[ToolError],
        expected_message: str,
        is_async: bool,
    ) -> None:
        """Jinja2's own text quotes what the template reached for, a key of the data included: the render writes it fixed."""
        error = await _render_failure(template_source=template_source, context=context, is_async=is_async)

        assert isinstance(error, expected_error), topic
        assert str(error) == expected_message, topic
        assert "confidential" not in json.dumps(error.to_problem(view=ProblemView.OPERATOR).to_wire()), topic

    @pytest.mark.parametrize("is_async", [False, True], ids=["sync", "async"])
    @pytest.mark.parametrize(
        ("topic", "template_source", "context", "expected_message"),
        [
            (
                "an attribute the template spells",
                "{{ invoice.total.amount }}",
                {"invoice": {}},
                "Jinja2 render — undefined error: the template reads 'total', which is not defined (UndefinedError, at line 1 of the template)",
            ),
            (
                "a private name the template spells",
                "{{ record._secret }}",
                {"record": object()},
                "Jinja2 render — refused by the template sandbox: A template may not read '_secret' on a 'object' value.",
            ),
        ],
    )
    async def test_a_name_the_template_spells_is_kept(
        self, topic: str, template_source: str, context: dict[str, Any], expected_message: str, is_async: bool
    ) -> None:
        """A name the template itself writes is its own, and tells its author what to fix."""
        error = await _render_failure(template_source=template_source, context=context, is_async=is_async)

        assert str(error) == expected_message, topic
