"""The load-time walker that finds the private names a template reads, for a located validation error."""

import pytest

from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_private_names import detect_private_name_references
from pipelex.tools.jinja2.template_category import TemplateCategory

_ALLOWED = frozenset({"_stuff_name", "_content_class"})


def _detect(template_source: str, *, template_category: TemplateCategory = TemplateCategory.LLM_PROMPT) -> list[str]:
    return detect_private_name_references(
        template_category=template_category,
        template_source=template_source,
        allowed_private_names=_ALLOWED,
    )


class TestDetectPrivateNameReferences:
    @pytest.mark.parametrize(
        ("topic", "template_source", "expected"),
        [
            ("dot", "{{ doc._stuff }}", ["_stuff"]),
            ("bracket", "{{ doc['_content'] }}", ["_content"]),
            ("dunder_chain_in_evaluation_order", "{{ cycler.__init__.__globals__ }}", ["__init__", "__globals__"]),
            ("inside_a_block", "{% if doc %}{% for x in doc.items %}{{ x._secret }}{% endfor %}{% endif %}", ["_secret"]),
            ("repeated_once", "{{ doc._stuff }} {{ other._stuff }}", ["_stuff"]),
            ("allowed_metadata", "{{ doc._stuff_name }} {{ doc['_content_class'] }}", []),
            ("public_names", "{{ doc.title }} {{ doc['title'] }} {{ doc.get('x') }}", []),
            ("dynamic_key_is_invisible", "{% set key = '_stuff' %}{{ doc[key] }}", []),
            ("underscore_variable_name_is_not_an_attribute", "{{ _internal }}", []),
        ],
    )
    def test_detects(self, topic: str, template_source: str, expected: list[str]) -> None:
        assert _detect(template_source) == expected, topic

    def test_expression_category(self) -> None:
        assert _detect("{{ doc._stuff == 'x' }}", template_category=TemplateCategory.EXPRESSION) == ["_stuff"]

    def test_unparseable_template_raises(self) -> None:
        with pytest.raises(Jinja2DetectVariablesError):
            _detect("{{ doc._stuff ")
