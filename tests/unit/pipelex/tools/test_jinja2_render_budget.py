"""The render budget: every render spends from one budget, and an operation that would overdraw it is refused.

The refusals are checked at sizes that would take seconds, gigabytes or both without the budget, so a
hook that stops charging makes its test hang or run out of memory rather than pass: the class's
timeout turns that into a failure. The renders that must keep working are checked against Jinja's
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
from typing_extensions import override

from pipelex.base_exceptions import ErrorDomain
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.jinja2.exceptions import Jinja2TemplateBudgetError
from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.jinja2.jinja2_filters import markdown_to_html
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey
from pipelex.tools.jinja2.jinja2_render_budget import DEFAULT_RENDER_BUDGET_UNITS, RenderBudgetExceededError, active_render_budget
from pipelex.tools.jinja2.jinja2_render_charging import CHARGED_MARK, INTERNAL_FILTERS
from pipelex.tools.jinja2.jinja2_render_costs import FILTER_COSTS, PLAIN_VALUE_METHOD_COSTS, REFUSED_PLAIN_VALUE_METHODS, TEST_COSTS
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async, render_jinja2_sync
from pipelex.tools.jinja2.jinja2_sandbox import PipelexTemplateEnvironment
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.markdown.markdown_parser import render_markdown_as_html
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
    pytest.param("{{ '%(a(b))1000000000s' % {'a(b)': 'x'} }}", id="percent_width_after_a_nested_key"),
    pytest.param("{{ lipsum(n=1000000000, min=-100, max=-99) }}", id="lipsum_negative_bounds"),
    pytest.param("{{ 'x' * (10 ** 9) }}", id="repeat_string"),
    pytest.param("{{ ([0] * (10 ** 9)) | length }}", id="repeat_list"),
    pytest.param("{{ 2 ** (10 ** 9) }}", id="power"),
    pytest.param("{{ '%1000000000d' % 1 }}", id="percent_width"),
    pytest.param("{{ '%.1000000000f' % 1.0 }}", id="percent_precision"),
    pytest.param("{{ '%*d' % (1000000000, 1) }}", id="percent_star_width"),
    pytest.param("{{ '%1000000000d' | format(1) }}", id="format_filter_width"),
    pytest.param("{{ ['%1000000000s'] | format('x') | length }}", id="format_filter_on_a_list"),
    pytest.param("{{ '{:>1000000000}'.format(1) }}", id="str_format_width"),
    pytest.param("{{ '{:>{w}}'.format(1, w=1000000000) }}", id="str_format_nested_width"),
    pytest.param("{{ '{:>{w}}'.format(1, w='1000000000') }}", id="str_format_nested_text_width"),
    pytest.param("{{ '{a:>{w}}'.format_map({'a': 1, 'w': 1000000000}) }}", id="format_map_width"),
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
    pytest.param("{{ (range(1000) | list) | replace('', 'y' * 200000) | length }}", id="replace_filter_on_a_list"),
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
    pytest.param("{% for i in range(100) %}{% set v = [" + ", ".join(["i"] * 1000) + "] %}{% endfor %}", id="list_literal_in_loop"),
    pytest.param("{% for i in range(100) %}{% set v = (" + ", ".join(["i"] * 1000) + ") %}{% endfor %}", id="tuple_literal_in_loop"),
    pytest.param("{% set t = ((1,) * 200,) * 200 %}{% for i in range(30) %}{% set d = {t: i} %}{% endfor %}", id="dict_literal_hashing_a_tuple"),
    pytest.param("{% set t = ((1,) * 200,) * 200 %}{% set d = {} %}{% for i in range(30) %}{{ d[t] }}{% endfor %}", id="item_read_hashing_a_tuple"),
    pytest.param("{% set x = '<>' * 200 %}{% for i in range(500) %}{% set s = x | striptags %}{% endfor %}", id="striptags_in_loop"),
    pytest.param("{% set x = ('<>' * 200) | safe %}{% for i in range(500) %}{% set s = x.striptags() %}{% endfor %}", id="markup_striptags_in_loop"),
    pytest.param("{% set x = 'a' * 400 %}{% for i in range(100) %}{% set s = x | wordwrap(1) %}{% endfor %}", id="wordwrap_in_loop"),
    pytest.param("{% set ll = [[0]] * 100 %}{% for i in range(50) %}{% set s = ll | sum(start=[]) %}{% endfor %}", id="sum_in_loop"),
    pytest.param("{% for i in range(5) %}{% set s = lipsum(n=10000, min=-100, max=-99) %}{% endfor %}", id="lipsum_in_loop"),
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


def _text_content(text: str) -> TextContent:
    return TextContent(text=text)


# Single steps that repeat an object of the run's data, whose text only converting it tells: each is
# refused before it allocates what the repetition asks, a few hundred megabytes.
_DATA_AMPLIFIERS = [
    pytest.param("{{ ([doc] * 20000) | join | length }}", id="join"),
    pytest.param("{{ (('%(a)s' * 20000) % {'a': doc}) | length }}", id="percent"),
    pytest.param("{{ ('{0.text}' * 20000).format(doc) | length }}", id="str_format_field"),
    pytest.param("{{ ('{a}' * 20000).format_map({'a': doc}) | length }}", id="format_map"),
    pytest.param("{{ links | urlize(target='t' * 2000) | length }}", id="urlize"),
    pytest.param("{{ (blob * 200000000) | length }}", id="bytes_repetition"),
]

# Ordering filters over long strings that share a prefix: few elements, each comparison scans them all.
_ORDERINGS = [
    pytest.param("{{ same | unique | list | length }}", id="unique"),
    pytest.param("{{ docs | sort(attribute='text') | length }}", id="sort_by_an_object_attribute"),
    pytest.param("{{ docs | sort(attribute='text', case_sensitive=true) | length }}", id="sort_by_an_object_attribute_case_sensitive"),
    pytest.param("{{ items | sort | length }}", id="sort"),
    pytest.param("{{ items | min | length }}", id="min"),
    pytest.param("{{ items | max(case_sensitive=true) | length }}", id="max"),
    pytest.param("{{ keyed | dictsort | length }}", id="dictsort"),
    pytest.param("{{ rows | groupby('k', case_sensitive=true) | list | length }}", id="groupby"),
]

# Operations that read a fixed part of a large value, repeated: each would overdraw the default budget
# if it were charged the whole value.
_FIXED_READS = [
    pytest.param("{% for i in range(100) %}{{ doc | length }}{{ doc | first }}{{ doc | last }}{% endfor %}", id="length_first_last"),
    pytest.param("{% for i in range(100) %}{{ lookup.get('k5') }}{{ lookup.keys() | length }}{% endfor %}", id="dict_get_and_keys"),
    pytest.param("{% for i in range(100) %}{% if doc is defined and doc is string %}y{% endif %}{% endfor %}", id="tests"),
    pytest.param("{% macro m(x) %}.{% endmacro %}{% for i in range(100) %}{{ m(doc) }}{% endfor %}", id="macro_argument"),
    pytest.param("{% for i in range(100) %}{{ doc.startswith('x') }}{{ doc | default('d') | length }}{% endfor %}", id="startswith_and_default"),
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
    pytest.param(
        "{{ nope | default('d') }}|{{ nope | length }}|{{ '-'.join(nope) }}|{{ 'a' in nope }}|{% for x in nope %}x{% else %}empty{% endfor %}",
        id="undefined_values",
    ),
    pytest.param("{% macro m(v) %}{{ v is defined }}{% endmacro %}{{ m(nope) }}", id="undefined_macro_argument"),
    pytest.param(
        "{% macro show(l) %}[{{ l.index }}/{{ l.length }}]{% endmacro %}{% for i in range(3) %}{{ show(loop) }}{% endfor %}",
        id="loop_passed_to_a_macro",
    ),
    pytest.param("{{ '{:>{w}}|{a}'.format('x', w='3', a=[1]) }}|{{ '{a:>{w}}'.format_map({'a': 'y', 'w': 2}) }}", id="format_fields"),
    pytest.param(
        "{{ ['b', 'A', 'a'] | sort | join }}|{{ [{'k': 'b'}, {'k': 'a'}] | sort(attribute='k') | map(attribute='k') | join }}"
        "|{{ ['b', 'A'] | min }}|{{ {'b': 1, 'A': 2} | dictsort(by='value') }}",
        id="orderings",
    ),
]


_STYLE = TemplatingStyle(tag_style=TagStyle.XML, text_format=TextFormat.PLAIN)


# A table whose two hundred columns pad three hundred one-character rows: sixty thousand cells, about sixty
# megabytes of parsed tokens, out of two kilobytes of text.
_PADDED_TABLE = "'|' ~ ('a|' * 222) ~ '\\n|' ~ ('-|' * 222) ~ '\\n' ~ ('|a\\n' * 300) ~ '\\n'"

# Markdown a template converts with the `markdown` filter, each refused before it parses or renders what it
# asks: a long source, which costs microseconds a character to parse; padded tables, which cost their cells;
# and a reference used thousands of times, whose destination is printed at every use.
_MARKDOWN_AMPLIFIERS = [
    pytest.param("{{ ('**a ' * 100000) | markdown }}", id="long_source"),
    pytest.param("{{ ((" + _PADDED_TABLE + ") * 3) | markdown }}", id="padded_tables"),
    pytest.param("{{ ('[a][r] ' * 2000 ~ '\\n\\n[r]: /' ~ 'y' * 20000) | markdown }}", id="reused_reference"),
]

# What a refused conversion may hold before the refusal: the source and its table scan, never its tokens
# or its output.
_MARKDOWN_REFUSAL_PEAK_BYTES = 32 * 1024 * 1024

# A Markdown value an HTML template converts again at every print, escape, join or format, the last only in
# async mode, where Pipelex's own `format` filter is registered.
_MARKDOWN_CONVERSIONS = [
    *(
        pytest.param(template_source, is_async, id=f"{name}-{'async' if is_async else 'sync'}")
        for name, template_source in (
            ("print", "{% for i in range(100) %}{{ report }}{% endfor %}"),
            ("escape", "{% for i in range(100) %}{{ report | e }}{% endfor %}"),
            ("join", "{{ ([report] * 100) | join }}"),
        )
        for is_async in (False, True)
    ),
    pytest.param("{% for i in range(100) %}{{ report | format }}{% endfor %}", True, id="format-async"),
]

_MARKDOWN_REPORT = "## Findings\n\nSome *text* with a [link](https://a.co), `code` and more.\n\n- one\n- two\n\n" * 300

_MARKDOWN_SAMPLE = (
    "# Report\n\n| a | b |\n| :- | -: |\n| 1 | 2 |\n| 3 |\n\n> quoted **bold** and ~~gone~~\n\n"
    'See [the docs][docs] and [again][docs], ![a chart](https://a.co/c.png "Chart"), https://a.co & <tags>.\n\n'
    "```python\nprint('<x>')\n```\n\n[docs]: https://a.co/docs \"The docs\"\n"
)


def _make_html_template(template_source: str, *, is_async: bool) -> Any:
    return make_jinja2_env_without_loader(TemplateCategory.HTML, enable_async=is_async).from_string(template_source)


def _render_html(template_source: str, *, is_async: bool, **context: Any) -> str:
    template = _make_html_template(template_source, is_async=is_async)
    context[Jinja2ContextKey.TEXT_FORMAT] = TextFormat.PLAIN
    if is_async:
        return cast("str", asyncio.run(template.render_async(**context)))
    return cast("str", template.render(**context))


class _Document:
    """An object of the run's data whose text is an attribute, read the way a filter reads it."""

    def __init__(self, text: str) -> None:
        self.text = text


class _Opaque:
    """An object of the run's data whose `repr` fails, as nothing a template does should call it."""

    @override
    def __repr__(self) -> str:
        msg = "repr taken"
        raise RuntimeError(msg)


@pytest.mark.timeout(60)
class TestRenderBudget:
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

    @pytest.mark.parametrize("template_source", _DATA_AMPLIFIERS)
    def test_repeated_data_is_refused_before_it_is_built(self, template_source: str) -> None:
        context: dict[str, Any] = {
            "doc": _text_content("x" * 10_000),
            "links": _text_content("a.com " * 10_000),
            "blob": b"x",
        }
        template = PipelexTemplateEnvironment(render_budget_units=_SMALL_BUDGET).from_string(template_source)
        assert _refused_render_peak_bytes(lambda: template.render(**context)) < 4 * _SMALL_BUDGET

    def test_rendering_with_images_is_estimated_item_by_item(self) -> None:
        template = make_jinja2_env_without_loader(TemplateCategory.LLM_PROMPT, enable_async=False).from_string(
            "{{ ([doc] * 30000) | with_images | length }}"
        )
        context: dict[str, Any] = {"doc": _text_content("x" * 10_000), Jinja2ContextKey.TEXT_FORMAT: TextFormat.PLAIN}
        assert _refused_render_peak_bytes(lambda: template.render(**context)) < DEFAULT_RENDER_BUDGET_UNITS

    @pytest.mark.parametrize("template_source", _ORDERINGS)
    def test_ordering_is_charged_for_its_comparisons(self, template_source: str) -> None:
        items = ["x" * 100_000 + str(index) for index in range(100)]
        context: dict[str, Any] = {
            "items": items,
            "keyed": dict.fromkeys(items, 1),
            "rows": [{"k": item} for item in items],
            "docs": [_Document(item) for item in items],
            "same": ["X" * 100_000] * 100,
        }
        with pytest.raises(RenderBudgetExceededError):
            _render(template_source, budget=_SMALL_BUDGET, **context)

    def test_comparing_models_weighs_their_fields(self) -> None:
        # Two equal texts of distinct strings, compared character by character; their models' `repr` is short.
        left = _text_content("x" * 2_000_000)
        right = _text_content("".join(["x" * 1_000_000, "x" * 1_000_000]))
        with pytest.raises(RenderBudgetExceededError):
            _render("{{ left == right }}", budget=_SMALL_BUDGET, left=left, right=right)

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
                templating_style=_STYLE,
            )

    @pytest.mark.asyncio
    async def test_deep_recursion_is_a_budget_error(self) -> None:
        with pytest.raises(Jinja2TemplateBudgetError, match="deeper than Python allows"):
            await render_jinja2_async(
                template_source="{% macro f(n) %}{{ f(n + 1) }}{% endmacro %}{{ f(0) }}",
                template_category=TemplateCategory.LLM_PROMPT,
                templating_context={},
                templating_style=_STYLE,
            )

    @pytest.mark.parametrize("template_source", _MARKDOWN_AMPLIFIERS)
    @pytest.mark.parametrize("is_async", [False, True])
    def test_markdown_conversion_refused_before_it_parses_or_renders(self, template_source: str, is_async: bool) -> None:
        peak_bytes = _refused_render_peak_bytes(lambda: _render_html(template_source, is_async=is_async))
        assert peak_bytes < _MARKDOWN_REFUSAL_PEAK_BYTES

    @pytest.mark.parametrize(("template_source", "is_async"), _MARKDOWN_CONVERSIONS)
    def test_markdown_value_is_charged_at_every_conversion(self, template_source: str, is_async: bool) -> None:
        # Each conversion of this report costs about a third of the default budget, and takes a few
        # milliseconds whatever it is charged: printed a hundred times, it is refused at the fourth.
        report = MarkdownContent(text=_MARKDOWN_REPORT)
        with pytest.raises(RenderBudgetExceededError, match="converting Markdown to HTML"):
            _render_html(template_source, is_async=is_async, report=report)

    @pytest.mark.parametrize("is_async", [False, True])
    def test_markdown_renders_as_outside_any_render(self, is_async: bool) -> None:
        rendered = _render_html(
            "{{ notes | markdown }}|{{ report }}", is_async=is_async, notes=_MARKDOWN_SAMPLE, report=MarkdownContent(text=_MARKDOWN_SAMPLE)
        )
        assert active_render_budget() is None
        expected = render_markdown_as_html(_MARKDOWN_SAMPLE)
        assert rendered == f"{expected}|{expected}"

    def test_markdown_the_budget_admits_parses_within_it(self) -> None:
        # Unclosed emphasis leaves a text token per delimiter, which markdown-it's own join held a copy of
        # every prefix of: thirty thousand characters peaked at over three hundred megabytes.
        tracemalloc.start()
        try:
            rendered = _render_html("{{ ('**a ' * 7500) | markdown }}", is_async=False)
            _, peak_bytes = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert len(rendered) > 30_000
        assert peak_bytes < _MARKDOWN_REFUSAL_PEAK_BYTES

    def test_the_active_budget_ends_with_its_render(self) -> None:
        with pytest.raises(RenderBudgetExceededError):
            _render_html("{{ ('**a ' * 100000) | markdown }}", is_async=False)
        assert active_render_budget() is None

    @pytest.mark.parametrize("method", ["count", "index"])
    @pytest.mark.parametrize("container", ["list", "tuple"])
    def test_searching_a_sequence_is_charged_for_its_comparisons(self, method: str, container: str) -> None:
        # Two equal strings that are distinct objects compare character by character.
        needle = "".join(["x" * 1000, "y"])
        items = ["x" * 1000 + "y" for _ in range(999)] + [needle]
        sequence: Any = items if container == "list" else tuple(items)
        with pytest.raises(RenderBudgetExceededError):
            _render(
                f"{{% for i in range(20) %}}{{% set c = seq.{method}(needle) %}}{{% endfor %}}", budget=_SMALL_BUDGET, seq=sequence, needle=needle
            )

    @pytest.mark.parametrize(
        "template_source", ["{{ big.values() }}", "{{ big.items() }}", "{{ 'a' ~ big.values() }}", "{{ big.values() | string }}"]
    )
    def test_a_dict_view_is_estimated_before_it_is_printed(self, template_source: str) -> None:
        big = {"k": ["x" * 1000] * 5000, **{f"k{index}": "y" * 1000 for index in range(2000)}}
        template = PipelexTemplateEnvironment(render_budget_units=_SMALL_BUDGET).from_string(template_source)
        assert _refused_render_peak_bytes(lambda: template.render(big=big)) < 4 * _SMALL_BUDGET

    @pytest.mark.parametrize("filter_name", ["upper", "lower", "capitalize", "title", "trim", "markdown"])
    def test_a_container_is_estimated_before_a_filter_converts_it(self, filter_name: str) -> None:
        env = PipelexTemplateEnvironment(autoescape=True, render_budget_units=_SMALL_BUDGET)
        env.filters["markdown"] = markdown_to_html
        template = env.from_string(f"{{{{ items | {filter_name} }}}}")
        assert _refused_render_peak_bytes(lambda: template.render(items=["x" * 1000] * 5000)) < 4 * _SMALL_BUDGET

    def test_a_percent_key_left_open_is_read_in_one_pass(self) -> None:
        # A quadratic scan of `%(` would take minutes here; Python refuses the format string at once.
        with pytest.raises(ValueError, match="incomplete format key"):
            _render("{{ ('%(' * 200000) % {} }}")

    def test_a_long_word_under_its_width_is_read_in_one_pass(self) -> None:
        # A run of non-space characters one short of the width is rescanned from every start by a pattern.
        template_source = "{{ (('a' * 199999 ~ ' ') * 2) | wordwrap(199999) | length }}"
        assert _render(template_source) == _render_stock(template_source)

    def test_stripping_tags_from_a_data_object_reads_its_text(self) -> None:
        text = "word " * 2400
        assert _render("{{ doc | striptags }}", doc=_text_content(text)) == _render("{{ text | striptags }}", text=text)

    def test_budget_error_is_the_caller_s_and_caller_facing(self) -> None:
        report = Jinja2TemplateBudgetError("refused by the render budget").to_error_report()
        assert report.error_domain == ErrorDomain.INPUT
        assert report.caller_facing_message

    @pytest.mark.parametrize("template_source", _UNCHANGED)
    @pytest.mark.parametrize("autoescape", [False, True])
    @pytest.mark.parametrize("is_async", [False, True])
    def test_renders_as_the_stock_sandbox(self, template_source: str, autoescape: bool, is_async: bool) -> None:
        context: dict[str, Any] = {"x": "<&>"}
        assert _render(template_source, autoescape=autoescape, is_async=is_async, **context) == _render_stock(
            template_source, autoescape=autoescape, is_async=is_async, **context
        )

    @pytest.mark.parametrize("template_source", _FIXED_READS)
    def test_reading_part_of_a_large_value_stays_cheap(self, template_source: str) -> None:
        context: dict[str, Any] = {"doc": "x" * 2_000_000, "lookup": {f"k{index}": index for index in range(100_000)}}
        assert _render(template_source, **context) == _render_stock(template_source, **context)

    @pytest.mark.parametrize("is_async", [False, True])
    def test_comparing_objects_never_takes_their_repr(self, is_async: bool) -> None:
        template_source = "{{ obj == obj }}|{{ obj in [obj] }}|{{ obj != 1 }}"
        context: dict[str, Any] = {"obj": _Opaque()}
        assert _render(template_source, is_async=is_async, **context) == _render_stock(template_source, is_async=is_async, **context)

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
