from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import BaseModel

from pipelex.base_exceptions import PipelexError
from pipelex.errors.problem import ProblemView
from pipelex.tools.jinja2.exceptions import (
    Jinja2TemplateBudgetError,
    Jinja2TemplateInvalidError,
    Jinja2TemplateRenderError,
    Jinja2TemplateSecurityError,
)
from pipelex.tools.jinja2.jinja2_render_budget import DEFAULT_RENDER_BUDGET_UNITS
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async, render_jinja2_sync
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.jinja2.template_owner import TemplateOwner
from pipelex.tools.jinja2.template_surface import TemplateSurface

# A value of the run's data, which no message, parameter or diagnostic carries.
_PAYLOAD = "confidential-patient-diagnosis"
# The same value as an identifier, which a template can also write as plain text.
_PAYLOAD_IDENTIFIER = "confidential_patient_diagnosis"


class _Record(BaseModel):
    """A value whose public methods a template reads but may not call."""

    label: str = "a label"


class _Chart:
    """A value declaring a method templates may call, named like the run's data, whose answer no render's budget affords."""

    __template_surface__ = TemplateSurface(callable_names=frozenset({_PAYLOAD_IDENTIFIER}), private_names=frozenset())

    def confidential_patient_diagnosis(self) -> range:
        return range(10**12)


# How the budget words a refusal, up to the call it refused.
_BUDGET_REFUSAL_PREFIX = (
    f"Jinja2 render — refused by the render budget: Rendering the template would spend more than its budget of {DEFAULT_RENDER_BUDGET_UNITS:,} "
    "work units: "
)


async def _render_failure(*, template_source: str, context: dict[str, Any], is_async: bool) -> PipelexError:
    """The error rendering `template_source` raises, through the synchronous or the asynchronous render.

    A `ToolError`, or for a refusal of the sandbox `Jinja2TemplateSecurityError`, which is a `SecurityError`.
    """
    if is_async:
        with pytest.raises(PipelexError) as async_exc_info:
            await render_jinja2_async(
                template_source=template_source,
                template_category=TemplateCategory.BASIC,
                templating_context=context,
                template_owner=TemplateOwner.METHOD,
            )
        return async_exc_info.value
    with pytest.raises(PipelexError) as sync_exc_info:
        render_jinja2_sync(
            template_source=template_source,
            template_category=TemplateCategory.BASIC,
            templating_context=context,
            template_owner=TemplateOwner.METHOD,
        )
    return sync_exc_info.value


@pytest.mark.builds_problems_without_required_params(
    reason="renders outside any pipe, whose failure location names the pipe, and withholds a refused name the run's data gave"
)
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
                "a key of the data the template also writes as plain text",
                f"Patient {_PAYLOAD_IDENTIFIER}:\n{{{{ mapping[lookup].field }}}}",
                {"mapping": {}, "lookup": _PAYLOAD_IDENTIFIER},
                Jinja2TemplateRenderError,
                "Jinja2 render — undefined error: the template reads a value that is not defined (UndefinedError, at line 2 of the template)",
            ),
            (
                "a private name read by a key the template also writes as plain text",
                f"_{_PAYLOAD_IDENTIFIER} {{{{ record[lookup] }}}}",
                {"record": object(), "lookup": f"_{_PAYLOAD_IDENTIFIER}"},
                Jinja2TemplateSecurityError,
                "Jinja2 render — refused by the template sandbox: A template may not read an unsafe name on a 'object' value.",
            ),
            (
                "a callable stored in a namespace under a key of the data",
                "{% set ns = namespace({lookup: record.count}) %}{{ ns }}",
                {"record": [], "lookup": _PAYLOAD},
                Jinja2TemplateSecurityError,
                (
                    "Jinja2 render — refused by the template sandbox: A template may not store a method of a 'list' value in a namespace: "
                    "a namespace holds data only."
                ),
            ),
            (
                "a method called by a name of the data",
                "{{ (record | attr(lookup))() }}",
                {"record": _Record(), "lookup": "model_dump"},
                Jinja2TemplateSecurityError,
                (
                    "Jinja2 render — refused by the template sandbox: A template may not call a method of a '_Record' value: "
                    "templates read data and call methods of plain values only."
                ),
            ),
            (
                "a syntax error at a token of the template",
                f"{{{{ note {_PAYLOAD_IDENTIFIER} }}}}",
                {"note": "a note"},
                Jinja2TemplateInvalidError,
                "Jinja2 render — the template cannot render as written: syntax error at line 1.",
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
        expected_error: type[PipelexError],
        expected_message: str,
        is_async: bool,
    ) -> None:
        """Jinja2's own text quotes what the template reached for, a key of the data included: the render writes it fixed."""
        error = await _render_failure(template_source=template_source, context=context, is_async=is_async)

        assert isinstance(error, expected_error), topic
        assert str(error) == expected_message, topic
        assert "confidential" not in json.dumps(error.to_problem(view=ProblemView.OPERATOR).to_wire()), topic
        assert "confidential" not in json.dumps(error.to_problem(view=ProblemView.CALLER).to_wire()), topic
        if isinstance(error, Jinja2TemplateSecurityError):
            # The refused name is the data's, so the problem withholds it rather than pass it on as `name`.
            assert error.refused_name is None, topic
            caller = error.to_problem(view=ProblemView.CALLER)
            assert caller.params is not None, topic
            assert "name" not in caller.params.as_wire(), topic

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
            (
                "a private name the template writes as a literal key",
                "{{ record['_secret'] }}",
                {"record": object()},
                "Jinja2 render — refused by the template sandbox: A template may not read '_secret' on a 'object' value.",
            ),
            (
                "a callable stored in a namespace under a name the template spells",
                "{% set ns = namespace(helper=record.count) %}{{ ns }}",
                {"record": []},
                (
                    "Jinja2 render — refused by the template sandbox: A template may not store the method 'count' of a 'list' value "
                    "in a namespace, as 'helper': a namespace holds data only."
                ),
            ),
            (
                "a method the template calls by its name",
                "{{ record.model_dump() }}",
                {"record": _Record()},
                (
                    "Jinja2 render — refused by the template sandbox: A template may not call the method 'model_dump' of a '_Record' value: "
                    "templates read data and call methods of plain values only."
                ),
            ),
        ],
    )
    async def test_a_name_the_template_spells_is_kept(
        self, topic: str, template_source: str, context: dict[str, Any], expected_message: str, is_async: bool
    ) -> None:
        """A name the template itself writes is its own, and tells its author what to fix."""
        error = await _render_failure(template_source=template_source, context=context, is_async=is_async)

        assert str(error) == expected_message, topic

    async def test_a_text_format_named_by_the_data_is_never_quoted(self) -> None:
        """Pipelex's own filter refuses a format it does not know by listing those it knows, never the name it was handed."""
        error = await _render_failure(template_source="{{ note | format(lookup) }}", context={"note": "a note", "lookup": _PAYLOAD}, is_async=True)

        assert isinstance(error, Jinja2TemplateRenderError)
        assert (
            str(error) == "Jinja2 render — context error: 'Invalid text format: the format filter takes one of 'plain', 'markdown', 'html', 'json''"
        )
        assert "confidential" not in json.dumps(error.to_problem(view=ProblemView.OPERATOR).to_wire())

    @pytest.mark.parametrize("is_async", [False, True], ids=["sync", "async"])
    @pytest.mark.parametrize(
        ("topic", "template_source"),
        [
            ("a method read by a name of the data", "{{ (chart | attr(lookup))() }}"),
            ("a method read by a key of the data", "{{ chart[lookup]() }}"),
        ],
    )
    async def test_a_call_the_budget_refuses_by_a_name_of_the_data_quotes_none_of_it(self, topic: str, template_source: str, is_async: bool) -> None:
        """A call overrunning the budget names the method only where the template spells it: here the name is the data's."""
        context = {"chart": _Chart(), "lookup": _PAYLOAD_IDENTIFIER}

        error = await _render_failure(template_source=template_source, context=context, is_async=is_async)

        assert isinstance(error, Jinja2TemplateBudgetError), topic
        assert str(error).startswith(f"{_BUDGET_REFUSAL_PREFIX}calling a method of a '_Chart' value needs about "), topic
        assert "confidential" not in json.dumps(error.to_problem(view=ProblemView.OPERATOR).to_wire()), topic

    @pytest.mark.parametrize("is_async", [False, True], ids=["sync", "async"])
    async def test_a_call_the_budget_refuses_by_a_name_the_template_spells_names_it(self, is_async: bool) -> None:
        """The method the template calls by its own name tells its author which call overran the budget."""
        error = await _render_failure(template_source=f"{{{{ chart.{_PAYLOAD_IDENTIFIER}() }}}}", context={"chart": _Chart()}, is_async=is_async)

        assert isinstance(error, Jinja2TemplateBudgetError)
        assert str(error).startswith(f"{_BUDGET_REFUSAL_PREFIX}calling the method '{_PAYLOAD_IDENTIFIER}' of a '_Chart' value needs about ")
