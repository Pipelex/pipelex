"""A `method.schema_violation` item reads the registry's sentence with its `field_path` and its `finding`, never the code's title.

Pure unit tests: the parser, the verdict translation and the problem items, with no Pipelex boot.
"""

from typing import Any

import pytest
from mthds.protocol.problem.models import ProblemItem
from mthds.protocol.problem.registry import CoreCode

from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.errors.problem import ProblemView
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle_translation import translate_to_validate_bundle_error

_SOURCE = "hello.mthds"

# A PipeLLM structured through a preliminary text, whose synthetic step pipes the elaborator cannot add: the bundle
# already declares one of their codes. A rule of the language no field validator holds, found once the bundle is valid.
_SYNTHETIC_CODE_COLLISION_MTHDS = """
domain = "hello"
description = "Greet the visitor"

[concept.Greeting]
description = "A greeting"

[concept.Greeting.structure]
text = "The words of the greeting"

[pipe.say_hello]
type = "PipeLLM"
description = "Say hello"
output = "Greeting"
prompt = "Say hello to the visitor"
structuring_method = "preliminary_text"

[pipe.say_hello__draft_text]
type = "PipeLLM"
description = "Draft the greeting"
output = "Text"
prompt = "Draft a greeting"
"""


def _caller_items(*, verdict: ValidateBundleError) -> list[ProblemItem]:
    problem = verdict.to_problem(view=ProblemView.CALLER)
    assert problem.code == CoreCode.METHOD_INVALID
    assert problem.errors is not None
    return problem.errors


class TestSchemaViolationSentence:
    def test_an_elaborator_refusal_reads_its_field_path_and_its_finding(self) -> None:
        """A rule no field validator holds is located on the pipe it is about, and the item says what was found there."""
        with pytest.raises(ValidateBundleError) as raised, translate_to_validate_bundle_error():
            MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_SYNTHETIC_CODE_COLLISION_MTHDS, mthds_source=_SOURCE)

        [item] = _caller_items(verdict=raised.value)

        assert item.code == CoreCode.METHOD_SCHEMA_VIOLATION
        assert item.params is not None
        params = item.params.as_wire()
        assert params["field_path"] == "pipe.say_hello"
        finding = params["finding"]
        assert "collide with existing pipes in the bundle" in finding
        assert item.detail == f"The declaration at 'pipe.say_hello' breaks a rule of the language ({finding})."

    def test_an_item_about_the_bundle_as_a_whole_is_located_at_its_file(self) -> None:
        """An uncategorized item naming no declaration of the bundle names its file as where the rule is broken."""
        verdict = ValidateBundleError(
            message="bundle 'hello.mthds' failed validation",
            pipelex_bundle_blueprint_validation_errors=[
                PipelexBundleBlueprintValidationErrorData(source=_SOURCE, domain_code="hello", message="the bundle declares no pipe and no concept"),
            ],
        )

        [item] = _caller_items(verdict=verdict)

        assert item.code == CoreCode.METHOD_SCHEMA_VIOLATION
        assert item.detail == f"The declaration at '{_SOURCE}' breaks a rule of the language (the bundle declares no pipe and no concept)."
        assert item.params is not None
        assert item.params.as_wire() == {"field_path": _SOURCE, "finding": "the bundle declares no pipe and no concept"}

    @pytest.mark.parametrize(
        ("mthds_content", "expected_finding"),
        [
            pytest.param(
                'domain = "hello"\n[concept]\n"bad name" = "A concept whose code is not one"\n',
                "Concept validation error at 'concept': Value error, Concept code 'bad name' is not a valid concept code",
                id="invalid_concept_code",
            ),
            pytest.param(
                'domain = "hello"\nconcept = 5\n',
                "Concept validation error at 'concept': Input should be a valid dictionary",
                id="concept_not_a_table",
            ),
        ],
    )
    @pytest.mark.parametrize("mthds_source", [_SOURCE, None])
    def test_a_concept_declaration_item_names_its_key_path(self, mthds_content: str, expected_finding: str, mthds_source: str | None) -> None:
        """A concept declaration that breaks a rule is named by its key path, never by its file, and a `concept` that is no table is a verdict."""
        with pytest.raises(ValidateBundleError) as raised, translate_to_validate_bundle_error():
            MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content, mthds_source=mthds_source)

        [item] = _caller_items(verdict=raised.value)

        assert item.code == CoreCode.METHOD_SCHEMA_VIOLATION
        assert item.params is not None
        params: dict[str, Any] = item.params.as_wire()
        assert params == {"field_path": "concept", "finding": expected_finding}
        assert item.detail == f"The declaration at 'concept' breaks a rule of the language ({expected_finding})."
