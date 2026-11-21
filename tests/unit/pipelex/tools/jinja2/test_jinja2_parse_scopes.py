import jinja2
import pytest
from pytest_mock import MockerFixture

from pipelex.tools.jinja2.exceptions import Jinja2TemplateSyntaxError
from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.jinja2.jinja2_parsing import (
    are_authored_templates_trusted,
    check_jinja2_parsing,
    read_jinja2_template,
    sharing_template_parses,
    trusting_authored_templates,
)
from pipelex.tools.jinja2.template_category import TemplateCategory

TEMPLATE_SOURCE = "{% for item in doc.items %}{{ item.title }}{% endfor %}"
BROKEN_TEMPLATE_SOURCE = "{% for item in doc.items %}{{ item.title }}"


class TestJinja2ParseScopes:
    def test_a_sharing_scope_parses_each_template_once(self, mocker: MockerFixture) -> None:
        """Inside the scope every reading of one template, nested scopes included, gets one tree; outside, each reading parses."""
        parse_spy = mocker.spy(jinja2.Environment, "parse")
        with sharing_template_parses():
            first_tree = read_jinja2_template(
                jinja2_env=make_jinja2_env_without_loader(template_category=TemplateCategory.LLM_PROMPT), template_source=TEMPLATE_SOURCE
            )
            with sharing_template_parses():
                second_tree = read_jinja2_template(
                    jinja2_env=make_jinja2_env_without_loader(template_category=TemplateCategory.LLM_PROMPT), template_source=TEMPLATE_SOURCE
                )
            check_jinja2_parsing(template_source=TEMPLATE_SOURCE, template_category=TemplateCategory.LLM_PROMPT)
        assert second_tree is first_tree
        assert parse_spy.call_count == 1

        outside_tree = read_jinja2_template(
            jinja2_env=make_jinja2_env_without_loader(template_category=TemplateCategory.LLM_PROMPT), template_source=TEMPLATE_SOURCE
        )
        assert outside_tree is not first_tree
        assert parse_spy.call_count == 2

    def test_a_sharing_scope_remembers_no_failed_parse(self, mocker: MockerFixture) -> None:
        """A template that does not parse is refused at every reading, each parsing it again."""
        parse_spy = mocker.spy(jinja2.Environment, "parse")
        with sharing_template_parses():
            for _ in range(2):
                with pytest.raises(Jinja2TemplateSyntaxError):
                    check_jinja2_parsing(template_source=BROKEN_TEMPLATE_SOURCE)
        assert parse_spy.call_count == 2

    def test_a_trusting_scope_skips_the_parse_check_and_ends_with_its_block(self, mocker: MockerFixture) -> None:
        """Inside, a template that does not parse passes the parse check unparsed; outside, it is refused again."""
        parse_spy = mocker.spy(jinja2.Environment, "parse")
        assert not are_authored_templates_trusted()
        with trusting_authored_templates():
            assert are_authored_templates_trusted()
            check_jinja2_parsing(template_source=BROKEN_TEMPLATE_SOURCE)
        assert parse_spy.call_count == 0
        assert not are_authored_templates_trusted()
        with pytest.raises(Jinja2TemplateSyntaxError):
            check_jinja2_parsing(template_source=BROKEN_TEMPLATE_SOURCE)
