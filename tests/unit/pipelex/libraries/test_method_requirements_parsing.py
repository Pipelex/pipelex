import pytest

from pipelex.core.method_trees.requirements_file import parse_requirements_text
from tests.unit.pipelex.libraries.test_data import MethodRequirementsTestData


class TestMethodRequirementsParsing:
    @pytest.mark.parametrize(("topic", "line", "name"), MethodRequirementsTestData.ACCEPTED_LINES)
    def test_a_pep_508_requirement_is_declared(self, topic: str, line: str, name: str) -> None:
        """A line holding exactly one PEP 508 requirement, markers and extras included, declares it, stripped."""
        parsed = parse_requirements_text(text=f"{line}\n")

        assert parsed.refused_lines == [], topic
        (requirement_line,) = parsed.requirements
        assert requirement_line.line_number == 1
        assert requirement_line.text == line.strip()
        assert requirement_line.requirement.name == name

    @pytest.mark.parametrize(("topic", "line", "reason_fragment"), MethodRequirementsTestData.REFUSED_LINES)
    def test_a_line_the_standard_refuses_is_named_with_why(self, topic: str, line: str, reason_fragment: str) -> None:
        """A URL, an option, a comment after a requirement, a continued line and anything else not PEP 508 are refused."""
        parsed = parse_requirements_text(text=f"pandas>=2\n{line}\n")

        assert [requirement_line.text for requirement_line in parsed.requirements] == ["pandas>=2"], topic
        (refused_line,) = parsed.refused_lines
        assert refused_line.line_number == 2
        assert refused_line.text == line.strip()
        assert reason_fragment in refused_line.reason

    def test_blank_lines_and_comments_declare_nothing_and_lines_keep_their_numbers(self) -> None:
        """A byte order mark is skipped, a carriage return ends a line, and a comment may be indented by spaces or tabs."""
        text = "﻿# data handling\r\n\r\n  # indented\n\t# tabbed\n   \npandas>=2.2\r\nopenpyxl\n"

        parsed = parse_requirements_text(text=text)

        assert parsed.refused_lines == []
        assert [(requirement_line.line_number, requirement_line.text) for requirement_line in parsed.requirements] == [
            (6, "pandas>=2.2"),
            (7, "openpyxl"),
        ]

    def test_every_refused_line_is_kept_not_only_the_first(self) -> None:
        """The author fixes the whole file in one pass, so each refused line is reported, in file order."""
        parsed = parse_requirements_text(text="-r base.txt\npandas\nname @ https://example.com/x.whl\n-e .\n")

        assert [refused_line.line_number for refused_line in parsed.refused_lines] == [1, 3, 4]
        assert [requirement_line.text for requirement_line in parsed.requirements] == ["pandas"]
