from typing import ClassVar

import pytest

from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_read_paths, detect_jinja2_required_variables
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.string_utils import get_root_from_dotted_path


class ReadPathsTestData:
    """Templates, and the dotted paths through which each reads its inputs."""

    CASES: ClassVar[list[tuple[str, str, set[str]]]] = [
        ("nested attribute", "{{ doc.a.b }}", {"doc.a.b"}),
        ("bare input", "{{ doc }}", {"doc"}),
        ("loop over an input", "{% for page in pages %}{{ page.text }}{% endfor %}", {"pages"}),
        ("set binding", "{% set part = doc.a %}{{ part.b }}", {"doc.a"}),
        ("subscript stops the path", "{{ doc.items[0].text }}", {"doc.items"}),
        ("filter keeps the path", "{{ doc.a | upper }}", {"doc.a"}),
        ("accessor called on an artefact", '{{ doc.get("a") }}', {"doc", "doc.get"}),
        (
            "method called on a mapping field",
            "{% for key, value in doc.mapping.items() %}{{ value }}{% endfor %}",
            {"doc.mapping", "doc.mapping.items"},
        ),
        ("method called on a bound name", '{% for page in pages %}{{ page.get("a") }}{% endfor %}', {"pages"}),
        ("global call reads only its arguments", "{% for index in range(count) %}{{ index }}{% endfor %}", {"count"}),
    ]


class TestDetectJinja2ReadPaths:
    @pytest.mark.parametrize(("topic", "template_source", "expected_paths"), ReadPathsTestData.CASES)
    def test_read_paths(self, topic: str, template_source: str, expected_paths: set[str]) -> None:
        read_paths = detect_jinja2_read_paths(template_category=TemplateCategory.LLM_PROMPT, template_source=template_source)

        assert read_paths == expected_paths, topic

    @pytest.mark.parametrize(("topic", "template_source", "expected_paths"), ReadPathsTestData.CASES)
    def test_the_roots_are_the_required_variables_roots(self, topic: str, template_source: str, expected_paths: set[str]) -> None:
        """A read path adds the object a method is called on, which never adds a root: the inputs required stay the same."""
        read_roots = {
            get_root_from_dotted_path(path)
            for path in detect_jinja2_read_paths(template_category=TemplateCategory.LLM_PROMPT, template_source=template_source)
        }
        required_roots = {
            get_root_from_dotted_path(path)
            for path in detect_jinja2_required_variables(template_category=TemplateCategory.LLM_PROMPT, template_source=template_source)
        }

        assert read_roots == required_roots == {get_root_from_dotted_path(path) for path in expected_paths}, topic
