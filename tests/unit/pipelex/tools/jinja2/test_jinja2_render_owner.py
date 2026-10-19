from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import INTERNAL_ERROR_PLACEHOLDER, DisclosureMode, PipelexError
from pipelex.system.exceptions import ToolError
from pipelex.tools.jinja2.exceptions import (
    Jinja2StuffError,
    Jinja2TemplateBudgetError,
    Jinja2TemplateInvalidError,
    Jinja2TemplateRenderError,
    Jinja2TemplateSecurityError,
)
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async, render_jinja2_sync
from pipelex.tools.jinja2.jinja2_unknown_names import find_unknown_filters_and_tests
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.jinja2.template_owner import TemplateOwner
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat

if TYPE_CHECKING:
    from pipelex.errors.error_codes import ErrorCode

_TEMPLATING_STYLE = TemplatingStyle(tag_style=TagStyle.NO_TAG, text_format=TextFormat.PLAIN)

# A filter the environment lacks inside a branch: it compiles, and only rendering the branch finds it.
_UNKNOWN_FILTER_IN_A_BRANCH = "{% if lane %}{{ lane | frob_the_lane }}{% else %}quietly_routed{% endif %}"
# The same filter outside any branch: compiling the template finds it.
_UNKNOWN_FILTER_AT_THE_TOP = "{{ lane | frob_the_lane }}"
# An unknown test inside a branch.
_UNKNOWN_TEST_IN_A_BRANCH = "{% if lane %}{% if lane is frobbed %}a{% endif %}{% endif %}"


async def _render_failure(
    template_source: str,
    *,
    template_owner: TemplateOwner,
    context: dict[str, Any] | None = None,
    category: TemplateCategory = TemplateCategory.LLM_PROMPT,
    is_undefined_strict: bool = False,
) -> PipelexError:
    # The sandbox's refusal is a `SecurityError`, not a `ToolError`: every other render failure is a `ToolError`.
    with pytest.raises((ToolError, Jinja2TemplateSecurityError)) as exc_info:
        await render_jinja2_async(
            template_source=template_source,
            template_category=category,
            templating_context={"lane": "express"} if context is None else context,
            templating_style=_TEMPLATING_STYLE,
            is_undefined_strict=is_undefined_strict,
            template_owner=template_owner,
        )
    return exc_info.value


class TestJinja2RenderOwner:
    @pytest.mark.parametrize(
        ("template_source", "fault"),
        [
            (_UNKNOWN_FILTER_IN_A_BRANCH, "No filter named 'frob_the_lane' found."),
            (_UNKNOWN_FILTER_AT_THE_TOP, "No filter named 'frob_the_lane'."),
            (_UNKNOWN_TEST_IN_A_BRANCH, "No test named 'frobbed' found."),
        ],
        ids=["filter_in_a_branch", "filter_at_compile", "test_in_a_branch"],
    )
    @pytest.mark.asyncio(loop_scope="class")
    async def test_an_invalid_method_template_is_the_methods_and_caller_facing(self, template_source: str, fault: str) -> None:
        """A method's template naming what its environment lacks: `method.template_invalid`, kept under STRICT, never quoting the source."""
        error = await _render_failure(template_source, template_owner=TemplateOwner.METHOD)

        assert isinstance(error, Jinja2TemplateInvalidError)
        assert isinstance(error, Jinja2TemplateRenderError)
        assert error.fault == fault
        report = error.to_error_report()
        assert report.code == CoreCode.METHOD_TEMPLATE_INVALID
        assert report.message == f"Jinja2 render — the template cannot render as written: {fault}"
        strict_payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert strict_payload["message"] == report.message
        assert "quietly_routed" not in strict_payload["message"]

    @pytest.mark.parametrize("template_source", [_UNKNOWN_FILTER_IN_A_BRANCH, _UNKNOWN_FILTER_AT_THE_TOP])
    @pytest.mark.asyncio(loop_scope="class")
    async def test_an_invalid_pipelex_template_is_ours_and_withheld(self, template_source: str) -> None:
        """Pipelex's own template, the default owner: `runtime.unexpected`, whose message STRICT withholds."""
        error = await _render_failure(template_source, template_owner=TemplateOwner.PIPELEX)

        assert isinstance(error, Jinja2TemplateInvalidError)
        report = error.to_error_report()
        assert report.code == CoreCode.RUNTIME_UNEXPECTED
        assert report.to_dict(disclosure_mode=DisclosureMode.STRICT)["message"] == INTERNAL_ERROR_PLACEHOLDER

    @pytest.mark.parametrize(
        ("topic", "template_source", "context", "is_undefined_strict", "error_class", "method_code", "pipelex_code"),
        [
            (
                "undefined_value",
                "{{ missing.name }}",
                {},
                True,
                Jinja2TemplateRenderError,
                CoreCode.PIPE_TEMPLATE_RENDER_FAILED,
                CoreCode.RUNTIME_UNEXPECTED,
            ),
            (
                "filter_refusing_a_value_of_the_run",
                "{{ lane | reverse }}",
                {"lane": 42},
                False,
                Jinja2TemplateRenderError,
                CoreCode.PIPE_TEMPLATE_RENDER_FAILED,
                CoreCode.RUNTIME_UNEXPECTED,
            ),
            (
                "arithmetic",
                "{{ 1 // 0 }}",
                {},
                False,
                Jinja2TemplateRenderError,
                CoreCode.PIPE_TEMPLATE_RENDER_FAILED,
                CoreCode.RUNTIME_UNEXPECTED,
            ),
            (
                "unknown_text_format",
                "{{ lane | format('bogus') }}",
                {"lane": "express"},
                False,
                Jinja2TemplateRenderError,
                CoreCode.METHOD_TEMPLATE_INVALID,
                CoreCode.RUNTIME_UNEXPECTED,
            ),
            (
                "sandbox_refusal",
                "{{ lane.__class__ }}",
                {"lane": "express"},
                False,
                Jinja2TemplateSecurityError,
                CoreCode.SECURITY_TEMPLATE_REFUSED,
                CoreCode.RUNTIME_UNEXPECTED,
            ),
            (
                "render_budget",
                "{{ 'x' * (10 ** 9) }}",
                {},
                False,
                Jinja2TemplateBudgetError,
                CoreCode.PIPE_TEMPLATE_BUDGET_EXCEEDED,
                CoreCode.INPUT_TOO_LARGE,
            ),
            (
                "reserved_context_key",
                "{{ lane }}",
                {"lane": "express", Jinja2ContextKey.TAG_STYLE: "taken"},
                False,
                Jinja2StuffError,
                CoreCode.METHOD_NAME_CONFLICT,
                CoreCode.RUNTIME_UNEXPECTED,
            ),
        ],
    )
    @pytest.mark.asyncio(loop_scope="class")
    async def test_each_failure_takes_its_owners_code(
        self,
        topic: str,
        template_source: str,
        context: dict[str, Any],
        is_undefined_strict: bool,
        error_class: type[PipelexError],
        method_code: ErrorCode,
        pipelex_code: ErrorCode,
    ) -> None:
        """The same failure is the method's on a method's template and ours, or the data's, on Pipelex's own."""
        for template_owner, expected_code in ((TemplateOwner.METHOD, method_code), (TemplateOwner.PIPELEX, pipelex_code)):
            error = await _render_failure(
                template_source,
                template_owner=template_owner,
                context=context,
                category=TemplateCategory.BASIC,
                is_undefined_strict=is_undefined_strict,
            )
            assert type(error) is error_class, topic
            assert error.to_error_report().code == expected_code, f"{topic} on a {template_owner} template"

    def test_the_sync_render_is_coded_alike(self) -> None:
        with pytest.raises(Jinja2TemplateInvalidError) as exc_info:
            render_jinja2_sync(
                template_source=_UNKNOWN_FILTER_IN_A_BRANCH,
                template_category=TemplateCategory.BASIC,
                templating_context={"lane": "express"},
                template_owner=TemplateOwner.METHOD,
            )
        assert exc_info.value.to_error_report().code == CoreCode.METHOD_TEMPLATE_INVALID

    @pytest.mark.parametrize(
        ("template_source", "expected_names"),
        [
            (_UNKNOWN_FILTER_IN_A_BRANCH, ["frob_the_lane"]),
            (_UNKNOWN_TEST_IN_A_BRANCH, ["frobbed"]),
            ("{{ lane | upper | frob }}{% if lane is defined and lane is frob %}{{ lane | frob }}{% endif %}", ["frob"]),
            ("{{ lane | upper | tag }}{% if lane is defined %}{{ lane | format }}{% endif %}", []),
        ],
    )
    def test_the_unknown_names_a_template_uses_are_found(self, template_source: str, expected_names: list[str]) -> None:
        assert find_unknown_filters_and_tests(template_source=template_source, template_category=TemplateCategory.LLM_PROMPT) == expected_names
