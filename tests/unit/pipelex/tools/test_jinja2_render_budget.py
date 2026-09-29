"""The render budget: every render spends from one budget, and an operation that would overdraw it is refused.

The refusals are checked at sizes that would take seconds, gigabytes or both without the budget, so a
hook that stops charging makes its test hang or run out of memory rather than pass: the timeout on
each class turns that into a failure. The renders that must keep working are checked against Jinja's
stock sandbox, which renders the same text with no budget at all.
"""

from __future__ import annotations

import asyncio
import inspect
import tracemalloc
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import jinja2.filters
import jinja2.tests
import pytest
from jinja2 import DictLoader
from jinja2.sandbox import ImmutableSandboxedEnvironment
from markupsafe import Markup

from pipelex.base_exceptions import ErrorDomain
from pipelex.tools.jinja2.exceptions import Jinja2TemplateBudgetError
from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.jinja2.jinja2_render_budget import DEFAULT_RENDER_BUDGET_UNITS, RenderBudgetExceededError
from pipelex.tools.jinja2.jinja2_render_charging import CHARGED_MARK, INTERNAL_FILTERS
from pipelex.tools.jinja2.jinja2_render_costs import FILTER_COSTS, PLAIN_VALUE_METHOD_COSTS, REFUSED_PLAIN_VALUE_METHODS, TEST_COSTS
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async, render_jinja2_sync
from pipelex.tools.jinja2.jinja2_sandbox import PipelexTemplateEnvironment
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat

if TYPE_CHECKING:
    from collections.abc import Callable

# A budget small enough that a repeated step overdraws it in a few milliseconds.
_SMALL_BUDGET = 1_000_000


def _render(template_source: str, *, budget: int | None = None, autoescape: bool = False, is_async: bool = False, **context: Any) -> str:
    kwargs: dict[str, Any] = {} if budget is None else {"render_budget_units": budget}
    env = PipelexTemplateEnvironment(autoescape=autoescape, enable_async=is_async, **kwargs)
    template = env.from_string(template_source)
    if is_async:
        return asyncio.run(template.render_async(**context))
    return template.render(**context)


def _render_stock(template_source: str, *, autoescape: bool = False, is_async: bool = False, **context: Any) -> str:
    template = ImmutableSandboxedEnvironment(autoescape=autoescape, enable_async=is_async).from_string(template_source)
    if is_async:
        return asyncio.run(template.render_async(**context))
    return template.render(**context)


def _refused_render_peak_bytes(render: Callable[[], object]) -> int:
    """Run a render the budget must refuse, and return the most memory it held on the way."""
    was_tracing = tracemalloc.is_tracing()
    if not was_tracing:
        tracemalloc.start()
    tracemalloc.reset_peak()
    try:
        with pytest.raises(RenderBudgetExceededError):
            render()
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        if not was_tracing:
            tracemalloc.stop()
    return peak_bytes


# Single steps whose result would be enormous, each refused before it runs, under the default budget.
_AMPLIFIERS = [
    pytest.param("{{ 'x' * (10 ** 9) }}", id="repeat_string"),
    pytest.param("{{ ([0] * (10 ** 9)) | length }}", id="repeat_list"),
    pytest.param("{{ 2 ** (10 ** 9) }}", id="power"),
    pytest.param("{{ '%1000000000d' % 1 }}", id="percent_width"),
    pytest.param("{{ '%.1000000000f' % 1.0 }}", id="percent_precision"),
    pytest.param("{{ '%*d' % (1000000000, 1) }}", id="percent_star_width"),
    pytest.param("{{ '%1000000000d' | format(1) }}", id="format_filter_width"),
    pytest.param("{{ '{:>1000000000}'.format(1) }}", id="str_format_width"),
    pytest.param("{{ '{:>{w}}'.format(1, w=1000000000) }}", id="str_format_nested_width"),
    pytest.param("{{ '{:.1000000000f}'.format(1.0) }}", id="str_format_precision"),
    pytest.param("{{ 'x'.ljust(1000000000) }}", id="ljust"),
    pytest.param("{{ 'x'.rjust(1000000000) }}", id="rjust"),
    pytest.param("{{ 'x'.center(1000000000) }}", id="center_method"),
    pytest.param("{{ 'x'.zfill(1000000000) }}", id="zfill"),
    pytest.param("{{ ('\\t' * 1000).expandtabs(1000000000) }}", id="expandtabs"),
    pytest.param("{{ ('x' * 1000).replace('x', 'y' * 10000000) }}", id="replace_method"),
    pytest.param("{{ ('x' * 100000).replace('', 'y' * 100000) }}", id="replace_method_empty_old"),
    pytest.param("{{ ('y' * 100000).join('x' * 1000000) }}", id="join_method"),
    pytest.param("{{ ('y' * 1000000).join(range(100000) | reverse) }}", id="join_method_lazy"),
    pytest.param("{{ ('a' * 100000).translate({97: 'x' * 100000}) }}", id="translate"),
    pytest.param("{{ ('ab ' * 30000000).split() | length }}", id="split"),
    pytest.param("{{ ('ab\\n' * 30000000).splitlines() | length }}", id="splitlines"),
    pytest.param("{{ 'x' | center(1000000000) }}", id="center_filter"),
    pytest.param("{{ ('x\\n' * 10) | indent(100000000) }}", id="indent_width"),
    pytest.param("{{ ('x\\n' * 1000000) | indent('y' * 10000) }}", id="indent_string"),
    pytest.param("{{ ('x ' * 1000000) | wordwrap(1, wrapstring='y' * 10000) }}", id="wordwrap_wrapstring"),
    pytest.param("{{ ('x' * 1000000) | wordwrap(1) }}", id="wordwrap_long_word"),
    pytest.param("{{ ('x' * 100000) | replace('', 'y' * 100000) }}", id="replace_filter"),
    pytest.param("{{ [1] | batch(1000000000, 'x') | list | length }}", id="batch_padding"),
    pytest.param("{{ [1] | slice(1000000000) | list | length }}", id="slice_count"),
    pytest.param("{{ range(100000) | join('x' * 100000) }}", id="join_filter"),
    pytest.param("{{ range(100000) | map('string') | join('x' * 100000) }}", id="join_filter_lazy"),
    pytest.param("{{ ([[0] * 1000] * 10000) | sum(start=[]) | length }}", id="sum_of_lists"),
    pytest.param("{{ ('<!---->' * 1000000) | striptags | length }}", id="striptags_comments"),
    pytest.param("{{ ('a.com ' * 100000) | urlize(target='t' * 100000) | length }}", id="urlize_target"),
    pytest.param("{{ lipsum(n=1000000000) }}", id="lipsum_paragraphs"),
    pytest.param("{{ lipsum(n=1, min=1000000000, max=1000000001) }}", id="lipsum_words"),
    pytest.param("{% set big = 'x' * 10000 %}{{ ([big] * 100000) | string | length }}", id="string_of_shared_list"),
    pytest.param("{% set big = 'x' * 10000 %}{{ [big] * 100000 }}", id="print_shared_list"),
    pytest.param("{% set big = 'x' * 10000 %}{{ ('y' ~ ([big] * 100000)) | length }}", id="concat_shared_list"),
    pytest.param("{% set big = 'x' * 10000 %}{{ ([big] * 100000) | tojson | length }}", id="tojson_shared_list"),
    pytest.param("{% set big = 'x' * 10000 %}{{ ([big] * 100000) | pprint | length }}", id="pprint_shared_list"),
    pytest.param("{% set big = 'x' * 10000 %}{{ '%s' % ([big] * 100000) }}", id="percent_shared_list"),
    pytest.param("{% set big = 'x' * 10000 %}{{ (big ~ '') in ([big] * 1000000) }}", id="in_shared_list"),
    pytest.param("{% set a = ['x' * 10000] * 500000 %}{% set b = ['x' * 10000 ~ ''] * 500000 %}{{ a == b }}", id="equal_shared_lists"),
    pytest.param("{{ range(0, 2305843009213693951 * 100000, 2305843009213693951) | unique | list | length }}", id="colliding_integers"),
    pytest.param("{{ range(2 ** 70, 2 ** 70 + 3) | list }}", id="range_of_wide_integers"),
    pytest.param("{{ ('9' * 4000) | int }}", id="int_filter_wide"),
]

# Steps that are cheap one at a time and overdraw a small budget when repeated. Each is sized so that
# only the charge it exercises can overdraw: its loop alone, at 64 units an element, stays well inside.
_REPEATED_STEPS = [
    pytest.param(
        "{% set ns = namespace(s='x') %}{% for i in range(40) %}{% set ns.s = ns.s ~ ns.s %}{% endfor %}{{ ns.s | length }}", id="doubling_namespace"
    ),
    pytest.param(
        "{% macro d(s, n) %}{% if n %}{{ d(s ~ s, n - 1) }}{% else %}{{ s | length }}{% endif %}{% endmacro %}{{ d('x', 40) }}", id="doubling_macro"
    ),
    pytest.param(
        "{% set ns = namespace(l=[]) %}{% for i in range(1000) %}{% set ns.l = ns.l + [i] %}{% endfor %}{{ ns.l | length }}", id="list_growth"
    ),
    pytest.param("{% set ns = namespace(x=3) %}{% for i in range(40) %}{% set ns.x = ns.x * ns.x %}{% endfor %}{{ ns.x }}", id="integer_squaring"),
    pytest.param(
        "{% for a in range(1000) %}{% for b in range(1000) %}{% for c in range(1000) %}{% endfor %}{% endfor %}{% endfor %}",
        id="empty_nested_range_loops",
    ),
    pytest.param(
        "{% set l = ('x' * 1000) | list %}{% for a in l %}{% for b in l %}{% for c in l %}{% endfor %}{% endfor %}{% endfor %}",
        id="empty_nested_list_loops",
    ),
    pytest.param("{% macro f(n) %}{% if n %}{{ f(n - 1) }}{{ f(n - 1) }}{% endif %}{% endmacro %}{{ f(40) }}", id="macro_fan_out"),
    pytest.param("{% for i in range(1000) %}" + "x" * 10000 + "{% endfor %}", id="static_text_in_loop"),
    pytest.param("{% set big = 'x' * 10000 %}{% for i in range(1000) %}{{ big }}{% endfor %}", id="printed_value_in_loop"),
    pytest.param("{% set big = 'x' * 100000 %}{% for i in range(100) %}{% set s = big[1:] %}{% endfor %}", id="slice_in_loop"),
    pytest.param(
        "{% set a = 'x' * 100000 %}{% set b = a ~ '' %}{% for i in range(100) %}{% if a == b %}{% endif %}{% endfor %}", id="equality_in_loop"
    ),
    pytest.param("{% set a = 'x' * 100000 %}{% for i in range(100) %}{% if 'y' in a %}{% endif %}{% endfor %}", id="substring_in_loop"),
    # Two lists of equal but distinct strings: small to hold, so charging the test's inputs stays cheap,
    # and costly to compare, which only the comparison's estimate sees.
    pytest.param(
        "{% set a = ['x' * 1000] * 1000 %}{% set b = ['x' * 1000 ~ ''] * 1000 %}{% for i in range(20) %}{% if a is eq b %}{% endif %}{% endfor %}",
        id="equality_test_in_loop",
    ),
    pytest.param(
        "{% set a = 'x' * 100000 %}{% set b = a ~ '' %}{% for i in range(100) %}{% if a <= b <= a %}{% endif %}{% endfor %}",
        id="chained_comparison_in_loop",
    ),
    # Reading `loop.depth0` costs nothing, and passing a range to `loop(x)` is charged at its size, a few bytes an
    # element: only charging the elements `loop(x)` draws can overdraw.
    pytest.param(
        "{% for x in [range(5000)] * 10 recursive %}{% if not loop.depth0 %}{{ loop(x) }}{% endif %}{% endfor %}",
        id="recursive_loop",
    ),
    pytest.param("{% for i in range(1000) %}{% set s = range(100) | map('string') | join %}{% endfor %}", id="filters_in_loop"),
    # A lazy input produces its elements as a filter draws them, at no cost any other charge sees: `reject`
    # draws every element `select` produces, and yields none.
    pytest.param("{% set s = range(1, 30000) | select | reject | first %}", id="lazy_input_drawn"),
    # `reject` draws a range at no charge per element, so only sizing the range by its length can overdraw.
    pytest.param("{% for i in range(100) %}{% set s = range(1, 100000) | reject | first %}{% endfor %}", id="range_drawn_by_a_filter"),
    pytest.param("{% for i in range(5000) %}{% set s = 'abc'.upper() %}{% endfor %}", id="method_calls_in_loop"),
    pytest.param("{% for i in range(5000) %}{% set s = [i] | first %}{% endfor %}", id="filter_calls_in_loop"),
    pytest.param("{% for i in range(10000) %}{% set t = i is odd %}{% endfor %}", id="test_calls_in_loop"),
]

# Templates that must render exactly as Jinja's stock sandbox renders them.
_UNCHANGED = [
    pytest.param("{{ 1 < 2 < 3 }}|{{ 3 > 2 > 2 }}|{{ 1 == 1.0 }}|{{ 'a' != 'b' }}", id="comparisons"),
    pytest.param("{{ 'a' in 'abc' }}|{{ 'd' not in ['a'] }}|{{ 1 in {1: 2} }}|{{ 2 in range(3) }}|{{ 5 in range(3) | reverse }}", id="membership"),
    # Parts that are not all constants: Jinja folds a constant `~` at compile time, which drops the markup.
    pytest.param("{{ x ~ ('<b>' | safe) ~ 1 ~ [2] }}|{{ x ~ x }}", id="concat_with_markup"),
    pytest.param("<p>{{ x }}</p>{{ '<i>' }}", id="static_text_and_escaping"),
    pytest.param("{{ 'abcdef'[1:3] }}|{{ [1, 2, 3][::-1] }}|{{ 'abc'[1] }}", id="slices"),
    pytest.param("{% for i in [1, 2, 3] %}{{ loop.index }}/{{ loop.length }}/{{ loop.revindex }}/{{ loop.last }};{% endfor %}", id="loop_helpers"),
    pytest.param("{% for x in range(3) | map('string') %}{{ loop.length }}{{ x }}{% endfor %}", id="loop_length_over_lazy_iterable"),
    pytest.param(
        "{% for i in range(5) if i is odd %}{{ i }}{% else %}none{% endfor %}|{% for i in [] %}x{% else %}none{% endfor %}", id="loop_test_and_else"
    ),
    pytest.param(
        "{% for x in [[1, [2]], 3] recursive %}{% if x is iterable %}[{{ loop(x) }}]{% else %}{{ x }}{% endif %}{% endfor %}", id="recursive_loop"
    ),
    pytest.param("{% macro wrap(x) %}[{{ x }}{{ caller() }}]{% endmacro %}{% call wrap(1) %}C{% endcall %}", id="macro_with_caller"),
    pytest.param("{% set x %}a{{ 1 }}{% endset %}{{ x }}{% filter upper %}b{{ 'c' }}{% endfilter %}", id="set_and_filter_blocks"),
    pytest.param("{{ 2 ** 10 }}|{{ 7 // 2 }}|{{ 7 % 3 }}|{{ 1.5 * 2 }}|{{ 'ab' * 3 }}|{{ [1] * 3 }}|{{ -3 + 1 }}|{{ 1 / 4 }}", id="arithmetic"),
    pytest.param("{{ '%05.1f|%s' % (3.14159, 'x') }}|{{ '%(a)s-%(a)s' % {'a': 1} }}", id="percent_format"),
    pytest.param("{{ '{:>5}|{}|{x:.2f}'.format('a', 2, x=1.5) }}|{{ '%d items' | format(3) }}", id="str_format"),
    pytest.param(
        "{{ 'a,b'.split(',') | join('-') }}|{{ 'x'.ljust(3) }}|{{ ' y '.strip() }}|{{ 'ab'.replace('a', 'c') }}|{{ ','.join(['1', '2']) }}",
        id="methods",
    ),
    pytest.param(
        "{{ [3, 1, 2] | sort | list }}|{{ [1, 1, 2] | unique | list }}|{{ [1, 2, 3] | batch(2) | list }}|{{ [1, 2, 3] | slice(2) | list }}",
        id="list_filters",
    ),
    pytest.param(
        "{{ {'b': 1, 'a': 2} | dictsort }}|{{ [1, 2, 3] | sum }}|{{ [1, 2] | min }}|{{ [1, 2] | max }}|{{ [1, 2] | first }}|{{ [1, 2] | last }}",
        id="aggregates",
    ),
    pytest.param(
        "{{ 'ab' | center(6) }}|{{ 'a\\nb' | indent(2) }}|{{ 'aaa bbb' | wordwrap(3) }}|{{ 'long text' | truncate(5, true, '') }}", id="text_filters"
    ),
    pytest.param(
        "{{ {'a': '<'} | tojson }}|{{ '<x>' | tojson }}|{{ [1, {'b': 2}] | pprint }}|{{ '<b>x</b>' | striptags }}", id="serialisation_filters"
    ),
    pytest.param("{{ '<' | escape }}|{{ 'a b' | urlencode }}|{{ 'see a.com' | urlize }}|{{ {'class': 'x'} | xmlattr }}", id="escaping_filters"),
    pytest.param(
        "{{ 'abc' | capitalize }}|{{ 'a b' | title }}|{{ ' a ' | trim }}|{{ 'a b c' | wordcount }}|{{ 1000 | filesizeformat }}",
        id="more_text_filters",
    ),
    pytest.param(
        "{{ '3' | int }}|{{ '1.5' | float }}|{{ 1.55 | round(1) }}|{{ -1 | abs }}|{{ 'abc' | reverse }}|{{ [1, 2] | reverse | list }}",
        id="number_filters",
    ),
    pytest.param("{{ x | default('d') }}|{{ [1, 2] | length }}|{{ {'a': 1} | items | list }}|{{ [1, 2] | string }}", id="misc_filters"),
    pytest.param(
        "{{ [{'a': 1}, {'a': 2}] | map(attribute='a') | select('odd') | list }}|{{ [{'a': 1}] | selectattr('a') | list | length }}",
        id="map_and_select",
    ),
    pytest.param("{{ [{'a': 1}, {'a': 1}] | groupby('a') | list | length }}|{{ [1, 2] | reject('odd') | list }}", id="groupby_and_reject"),
    pytest.param(
        "{{ 3 is odd }}{{ 'ab' is lower }}{{ nothing is defined }}{{ 2 is in [1, 2] }}{{ 1 is eq 1 }}{{ 2 is gt 1 }}{{ 'a' is string }}", id="tests"
    ),
    pytest.param("{% set ns = namespace(n=1) %}{% set ns.n = ns.n + 1 %}{{ ns.n }}|{{ dict(a=1)['a'] }}|{{ range(3) | list }}", id="globals"),
    pytest.param("{% set c = cycler('a', 'b') %}{{ c.next() }}{{ c.next() }}{% set j = joiner(',') %}{{ j() }}x{{ j() }}y", id="cycler_and_joiner"),
    pytest.param(
        "{{ (1).bit_length() }}|{{ 1.5.is_integer() }}|{{ {'a': 1}.get('a') }}|{{ [1, 2].index(2) }}|{{ (1, 2).count(1) }}", id="plain_methods"
    ),
]


@pytest.mark.timeout(60)
class TestRenderBudgetRefuses:
    @pytest.mark.parametrize("template_source", _AMPLIFIERS)
    @pytest.mark.parametrize("is_async", [False, True])
    def test_single_step_refused_before_it_runs(self, template_source: str, is_async: bool) -> None:
        # Refused after it ran, a step would still fail the render, having allocated gigabytes first. What
        # the render allocates before the refusal is its inputs, which fit in the budget.
        assert _refused_render_peak_bytes(lambda: _render(template_source, is_async=is_async)) < DEFAULT_RENDER_BUDGET_UNITS

    @pytest.mark.parametrize("template_source", _REPEATED_STEPS)
    @pytest.mark.parametrize("is_async", [False, True])
    def test_repeated_steps_overdraw(self, template_source: str, is_async: bool) -> None:
        with pytest.raises(RenderBudgetExceededError):
            _render(template_source, budget=_SMALL_BUDGET, is_async=is_async)

    @pytest.mark.parametrize("template_source", ["{{ big }}", "{{ ('' | safe) ~ big }}"])
    def test_escaped_text_is_estimated_before_it_is_escaped(self, template_source: str) -> None:
        # Printed under autoescape, or joined to markup, `<` grows fourfold: the text fits the budget, its
        # escaped form does not.
        template = PipelexTemplateEnvironment(autoescape=True, render_budget_units=_SMALL_BUDGET).from_string(template_source)
        big = "<" * 600_000
        assert _refused_render_peak_bytes(lambda: template.render(big=big)) < _SMALL_BUDGET

    @pytest.mark.parametrize("autoescape", [False, True])
    def test_escaping_is_estimated(self, autoescape: bool) -> None:
        # Printing, joining and escaping under autoescape grow `<` fourfold, which the estimate counts.
        with pytest.raises(RenderBudgetExceededError):
            _render("{{ big | escape }}{{ big ~ '' }}", budget=_SMALL_BUDGET, autoescape=autoescape, big="<" * 300_000)

    @pytest.mark.parametrize("view", ["keys", "values", "items"])
    def test_dict_view_is_sized_by_its_length(self, view: str) -> None:
        # A dict's view is a few bytes, and `reject` iterates all of it.
        template_source = f"{{% for i in range(100) %}}{{% set s = big.{view}() | reject | first %}}{{% endfor %}}"
        with pytest.raises(RenderBudgetExceededError):
            _render(template_source, budget=_SMALL_BUDGET, big={number: number for number in range(1, 100_000)})

    def test_included_template_spends_from_the_includer_budget(self) -> None:
        env = PipelexTemplateEnvironment(loader=DictLoader({"child": "{{ big }}"}), render_budget_units=_SMALL_BUDGET)
        template = env.from_string("{% for i in range(1000) %}{% include 'child' %}{% endfor %}")
        with pytest.raises(RenderBudgetExceededError):
            template.render(big="x" * 10_000)

    def test_caller_finalize_output_is_charged(self) -> None:
        def inflate(_value: object) -> str:
            return "y" * 100_000

        env = PipelexTemplateEnvironment(finalize=inflate, render_budget_units=_SMALL_BUDGET)
        with pytest.raises(RenderBudgetExceededError):
            env.from_string("{% for i in range(100) %}{{ i }}{% endfor %}").render()

    def test_refusal_names_the_operation_and_never_the_source(self) -> None:
        template_source = "{{ 'secret-marker'.ljust(1000000000) }}"
        with pytest.raises(RenderBudgetExceededError, match=r"calling the method 'ljust' of a 'str' value") as exc_info:
            _render(template_source)
        assert "secret-marker" not in str(exc_info.value)


@pytest.mark.timeout(60)
class TestRenderBudgetErrors:
    _STYLE = TemplatingStyle(tag_style=TagStyle.XML, text_format=TextFormat.PLAIN)

    def test_sync_render_raises_the_budget_error(self) -> None:
        with pytest.raises(Jinja2TemplateBudgetError, match="refused by the render budget"):
            render_jinja2_sync(template_source="{{ 'x' * (10 ** 9) }}", template_category=TemplateCategory.BASIC, templating_context={})

    @pytest.mark.asyncio
    async def test_async_render_raises_the_budget_error(self) -> None:
        with pytest.raises(Jinja2TemplateBudgetError, match="refused by the render budget"):
            await render_jinja2_async(
                template_source="{{ 'x' * (10 ** 9) }}",
                template_category=TemplateCategory.LLM_PROMPT,
                templating_context={},
                templating_style=self._STYLE,
            )

    @pytest.mark.asyncio
    async def test_deep_recursion_is_a_budget_error(self) -> None:
        with pytest.raises(Jinja2TemplateBudgetError, match="deeper than Python allows"):
            await render_jinja2_async(
                template_source="{% macro f(n) %}{{ f(n + 1) }}{% endmacro %}{{ f(0) }}",
                template_category=TemplateCategory.LLM_PROMPT,
                templating_context={},
                templating_style=self._STYLE,
            )

    def test_budget_error_is_the_caller_s_and_caller_facing(self) -> None:
        report = Jinja2TemplateBudgetError("refused by the render budget").to_error_report()
        assert report.error_domain == ErrorDomain.INPUT
        assert report.caller_facing_message


@pytest.mark.timeout(60)
class TestRenderBudgetKeepsRendering:
    @pytest.mark.parametrize("template_source", _UNCHANGED)
    @pytest.mark.parametrize("autoescape", [False, True])
    @pytest.mark.parametrize("is_async", [False, True])
    def test_renders_as_the_stock_sandbox(self, template_source: str, autoescape: bool, is_async: bool) -> None:
        context: dict[str, Any] = {"x": "<&>"}
        assert _render(template_source, autoescape=autoescape, is_async=is_async, **context) == _render_stock(
            template_source, autoescape=autoescape, is_async=is_async, **context
        )

    def test_each_render_gets_its_own_budget(self) -> None:
        env = PipelexTemplateEnvironment(render_budget_units=_SMALL_BUDGET)
        template = env.from_string("{{ big }}")
        # Each render spends most of its budget, which only works if every render gets a new one.
        for _ in range(3):
            assert len(template.render(big="x" * 700_000)) == 700_000

    def test_large_text_in_an_escaping_template(self) -> None:
        # A 20 MB string of plain text prints under autoescape: its escaped length is counted, not guessed.
        big = "a" * 20_000_000
        assert len(_render("{{ big }}{{ big | escape }}", autoescape=True, big=big)) == 40_000_000

    def test_caller_finalize_still_applies(self) -> None:
        def blank_none(value: object) -> object:
            return "" if value is None else value

        env = PipelexTemplateEnvironment(finalize=blank_none)
        assert env.from_string("{{ nothing }}|{{ none }}|{{ 1 }}").render(nothing=None) == "||1"

    def test_finalize_assigned_after_construction_is_refused(self) -> None:
        env = PipelexTemplateEnvironment()
        env.finalize = str
        with pytest.raises(RuntimeError, match="takes its finalize at construction"):
            env.from_string("{{ 1 }}")


class TestRenderBudgetCoverage:
    def test_every_jinja_filter_and_test_is_classified(self) -> None:
        filters = cast("dict[str, Callable[..., Any]]", jinja2.filters.FILTERS)
        tests = cast("dict[str, Callable[..., Any]]", jinja2.tests.TESTS)
        assert [name for name, function in filters.items() if function not in FILTER_COSTS] == []
        assert [name for name, function in tests.items() if function not in TEST_COSTS] == []

    @pytest.mark.parametrize("category", list(TemplateCategory))
    def test_every_registered_filter_and_test_is_charged(self, category: TemplateCategory) -> None:
        env = make_jinja2_env_without_loader(category)
        env.filters["late"] = jinja2.filters.FILTERS["upper"]
        env.from_string("{{ 1 }}")
        for name, function in env.filters.items():
            assert name in INTERNAL_FILTERS or getattr(function, CHARGED_MARK, False), name
        for name, function in env.tests.items():
            assert getattr(function, CHARGED_MARK, False), name

    def test_unclassified_filter_is_refused_before_any_template_compiles(self) -> None:
        env = PipelexTemplateEnvironment()
        env.filters["shout"] = str.upper
        with pytest.raises(TypeError, match="has no cost in the render budget's tables"):
            env.from_string("{{ 'a' }}")

    @pytest.mark.parametrize("plain_type", list(PLAIN_VALUE_METHOD_COSTS))
    def test_every_plain_method_is_classified(self, plain_type: type) -> None:
        """A method a later Python adds fails here until someone decides what it costs."""
        instance_methods = {
            name
            for name in dir(plain_type)
            if not name.startswith("_")
            and callable(member := inspect.getattr_static(plain_type, name))
            and not isinstance(member, (classmethod, staticmethod))
            and type(member).__name__ not in {"classmethod_descriptor", "builtin_function_or_method"}
        }
        allowed = set(PLAIN_VALUE_METHOD_COSTS[plain_type])
        refused = set(REFUSED_PLAIN_VALUE_METHODS.get(plain_type, {}))
        assert not allowed & refused
        assert instance_methods <= allowed | refused, sorted(instance_methods - allowed - refused)

    def test_plain_types_cover_the_sandbox(self) -> None:
        assert set(PLAIN_VALUE_METHOD_COSTS) == {
            str,
            Markup,
            int,
            bool,
            float,
            Decimal,
            date,
            datetime,
            time,
            timedelta,
            list,
            tuple,
            dict,
            set,
            frozenset,
        }
