"""Reading a method's `requirements.txt` as the MTHDS standard does: its requirements, and the lines it refuses.

The MTHDS standard (`mthds/docs/spec/method-tree.md`, "Python Dependencies: `requirements.txt`") lets a method declare
the Python packages its own Python needs in a `requirements.txt` at the root of its method tree: each line is blank, a
comment whose first character other than a space or a tab is `#`, or exactly one PEP 508 requirement, markers
included. A requirement naming a URL, an option of any kind (a line starting with `-`), a comment after a requirement
and a line continued with a backslash are refused, naming the line. Only the root's file declares anything.

This module is the file's grammar alone, with no notion of where a method runs: checking the requirements against the
environment a method's PipeFunc steps run in is `pipelex/libraries/method_requirements.py`, and a plugin stating the
packages of its sandbox receives the requirements as read here (`pipelex/plugins/pipe_func_package_offer_registry.py`).
"""

import re
from typing import NamedTuple

from packaging.requirements import InvalidRequirement, Requirement

REQUIREMENTS_FILE_NAME = "requirements.txt"

_UTF8_BOM = "﻿"

# A comment inside a line starts at a `#` that opens the line or follows whitespace, as pip reads one, so the fragment of
# a URL, such as `#sha256=…`, is not one.
_INLINE_COMMENT = re.compile(r"(^|\s+)#.*$")


class RequirementLine(NamedTuple):
    """A requirement of a `requirements.txt`, with its 1-based line number and its text as written, stripped."""

    line_number: int
    text: str
    requirement: Requirement


class RefusedRequirementsLine(NamedTuple):
    """A line of a `requirements.txt` the standard refuses, with why."""

    line_number: int
    text: str
    reason: str


class ParsedRequirements(NamedTuple):
    """What a `requirements.txt` declares: its requirements, and the lines it holds that the standard refuses."""

    requirements: list[RequirementLine]
    refused_lines: list[RefusedRequirementsLine]


def _refusal_reason(*, stripped: str) -> tuple[Requirement | None, str | None]:
    """The requirement a non-blank, non-comment line declares, or why the standard refuses the line."""
    if stripped.endswith("\\"):
        return None, "a line continued with a backslash is refused; write each requirement on a line of its own"
    if stripped.startswith("-"):
        return None, "an option line, such as -r, -e, -c or --index-url, is refused; write each package as a PEP 508 requirement"
    # The requirement is judged without the comment after it, so a comment that mentions a URL is not read as one.
    remainder = _INLINE_COMMENT.sub("", stripped).rstrip()
    try:
        requirement = Requirement(remainder)
    except InvalidRequirement as exc:
        if "://" in remainder:
            return None, "a requirement naming a URL is refused; name the package and the versions it accepts instead"
        parser_message = str(exc).splitlines()[0] if str(exc) else "it does not parse"
        return None, f"the line is not a PEP 508 requirement: {parser_message}"
    if requirement.url is not None:
        return None, "a requirement naming a URL is refused; name the package and the versions it accepts instead"
    if remainder != stripped:
        return None, "a comment after a requirement is refused; write the comment on a line of its own"
    return requirement, None


def parse_requirements_text(*, text: str) -> ParsedRequirements:
    """Read the lines of a `requirements.txt` as the MTHDS standard does, keeping every refused line rather than the first.

    A leading byte order mark is skipped, and a line may end with a carriage return before its line feed.
    """
    requirements: list[RequirementLine] = []
    refused_lines: list[RefusedRequirementsLine] = []
    text = text.removeprefix(_UTF8_BOM)
    for line_index, raw_line in enumerate(text.split("\n")):
        line_number = line_index + 1
        line = raw_line.removesuffix("\r")
        if not line.strip():
            continue
        if line.lstrip(" \t").startswith("#"):
            continue
        stripped = line.strip()
        requirement, reason = _refusal_reason(stripped=stripped)
        if requirement is not None:
            requirements.append(RequirementLine(line_number=line_number, text=stripped, requirement=requirement))
        elif reason is not None:
            refused_lines.append(RefusedRequirementsLine(line_number=line_number, text=stripped, reason=reason))
    return ParsedRequirements(requirements=requirements, refused_lines=refused_lines)
