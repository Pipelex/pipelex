from collections import Counter
from typing import TYPE_CHECKING, Any

import jinja2
import pytest
from kajson import kajson
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.pipe_operators.doc_gen.pipe_doc_gen_blueprint import PipeDocGenBlueprint
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.pipe_operators.judge.pipe_judge_blueprint import PipeJudgeBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_operators.search.pipe_search_blueprint import PipeSearchBlueprint
from pipelex.tools.jinja2.jinja2_parsing import sharing_template_parses, trusting_authored_templates

if TYPE_CHECKING:
    from collections.abc import Callable

# A template large enough that its parse is the cost of building its blueprint, as in a method that lays out a long report.
LARGE_SECTION = "<section><h2>{{ report.title }}</h2>{% for line in report.lines %}<p>{{ line }}</p>{% endfor %}</section>\n"
LARGE_TEMPLATE = "<h1>{{ report.title }}</h1>\n" + LARGE_SECTION * 400
LARGE_PROMPT = "Summarize the report $report.title, whose sections read:\n" + "Section: {{ report.body }}\n" * 600
SYSTEM_PROMPT = "You summarize the reports of {{ company }}."


def _counting_parses(*, mocker: MockerFixture) -> Counter[str]:
    """Count every Jinja2 parse by the source parsed, from now on."""
    parsed_sources: Counter[str] = Counter()
    original_parse: Callable[..., Any] = jinja2.Environment.parse

    def counting_parse(self: jinja2.Environment, source: str, *args: Any, **kwargs: Any) -> Any:
        parsed_sources[source] += 1
        return original_parse(self, source, *args, **kwargs)

    mocker.patch.object(jinja2.Environment, "parse", counting_parse)
    return parsed_sources


def _compose_kwargs(*, template: str) -> dict[str, Any]:
    return {"description": "Lay out the report", "inputs": {"report": "Text"}, "output": "Html", "template": template}


def _llm_kwargs(*, prompt: str) -> dict[str, Any]:
    return {
        "description": "Summarize the report",
        "inputs": {"report": "Text", "company": "Text"},
        "output": "Text",
        "system_prompt": SYSTEM_PROMPT,
        "prompt": prompt,
    }


# Each operator whose blueprint compares the variables its templates read with its declared inputs: a blueprint that
# passes the comparison, then the same blueprint with a template reading the undeclared input `other`.
TEMPLATE_INPUT_CHECK_CASES: list[tuple[str, type[PipeBlueprint], dict[str, Any], dict[str, Any]]] = [
    ("compose", PipeComposeBlueprint, _compose_kwargs(template=LARGE_TEMPLATE), _compose_kwargs(template=LARGE_TEMPLATE + "{{ other }}")),
    ("llm", PipeLLMBlueprint, _llm_kwargs(prompt=LARGE_PROMPT), _llm_kwargs(prompt=LARGE_PROMPT + "$other")),
    (
        "img_gen",
        PipeImgGenBlueprint,
        {"description": "Draw the scene", "inputs": {"scene": "Text"}, "output": "Image", "prompt": "A drawing of $scene"},
        {"description": "Draw the scene", "inputs": {"scene": "Text"}, "output": "Image", "prompt": "A drawing of $scene and $other"},
    ),
    (
        "search",
        PipeSearchBlueprint,
        {"description": "Search the news", "inputs": {"topic": "Text"}, "output": "SearchResult", "prompt": "News on $topic"},
        {"description": "Search the news", "inputs": {"topic": "Text"}, "output": "SearchResult", "prompt": "News on $topic and $other"},
    ),
    (
        "doc_gen",
        PipeDocGenBlueprint,
        {"description": "Print the report", "inputs": {"report": "Text"}, "output": "Document", "format": "pdf", "template": LARGE_TEMPLATE},
        {
            "description": "Print the report",
            "inputs": {"report": "Text"},
            "output": "Document",
            "format": "pdf",
            "template": LARGE_TEMPLATE + "{{ other }}",
        },
    ),
    (
        "judge",
        PipeJudgeBlueprint,
        {"description": "Judge the message", "inputs": {"message": "Text"}, "output": "YesNo", "prompt": "@message", "question": "Is it urgent?"},
        {
            "description": "Judge the message",
            "inputs": {"message": "Text"},
            "output": "YesNo",
            "prompt": "@message",
            "question": "Is it urgent for {{ other }}?",
        },
    ),
]


class TestTrustedBlueprintInputChecks:
    def test_a_trusted_decode_parses_no_compose_or_llm_template(self, mocker: MockerFixture) -> None:
        """Decoding a compose and an LLM blueprint, as a worker decodes a run's crate, parses no template under trust and each once without."""
        compose_blueprint = PipeComposeBlueprint.model_validate(_compose_kwargs(template=LARGE_TEMPLATE))
        llm_blueprint = PipeLLMBlueprint.model_validate(_llm_kwargs(prompt=LARGE_PROMPT))
        encoded = kajson.dumps([compose_blueprint, llm_blueprint])  # pyright: ignore[reportUnknownMemberType]

        parsed_sources = _counting_parses(mocker=mocker)
        with sharing_template_parses():
            decoded_untrusted = kajson.loads(encoded)  # pyright: ignore[reportUnknownMemberType]
        # Each template is parsed once for its input check, the parse shared with the parse check; the prompts' sigils
        # are rewritten first, so their parsed sources are not the authored ones.
        assert sum(parsed_sources.values()) == 3
        assert parsed_sources[LARGE_TEMPLATE] == 1

        parsed_sources.clear()
        with sharing_template_parses(), trusting_authored_templates():
            decoded_trusted = kajson.loads(encoded)  # pyright: ignore[reportUnknownMemberType]
        assert not parsed_sources, f"templates parsed in a trusted decode: {[source[:40] for source in parsed_sources]}"

        assert decoded_trusted == decoded_untrusted == [compose_blueprint, llm_blueprint]

    @pytest.mark.parametrize(("test_id", "blueprint_class", "accepted_kwargs", "undeclared_kwargs"), TEMPLATE_INPUT_CHECK_CASES)
    def test_only_an_untrusted_build_checks_the_template_inputs(
        self,
        mocker: MockerFixture,
        test_id: str,
        blueprint_class: type[PipeBlueprint],
        accepted_kwargs: dict[str, Any],
        undeclared_kwargs: dict[str, Any],
    ) -> None:
        """Outside trust a template reading an undeclared input is refused; under trust the blueprint is built without parsing any template."""
        with pytest.raises(ValidationError, match="other"):
            blueprint_class.model_validate(undeclared_kwargs)

        parsed_sources = _counting_parses(mocker=mocker)
        with trusting_authored_templates():
            accepted = blueprint_class.model_validate(accepted_kwargs)
            undeclared = blueprint_class.model_validate(undeclared_kwargs)
        assert not parsed_sources, test_id
        assert accepted.input_names == undeclared.input_names, test_id

        blueprint_class.model_validate(accepted_kwargs)
        assert parsed_sources, test_id

    def test_only_an_untrusted_build_checks_a_condition_expression(self, mocker: MockerFixture) -> None:
        """A condition's expression is parsed and compiled outside trust, which refuses one that does not parse; under trust neither runs."""
        condition_kwargs: dict[str, Any] = {
            "description": "Route on the category",
            "inputs": {"report": "Text"},
            "output": "Text",
            "outcomes": {"small": "process_small"},
            "default_outcome": "fail",
        }
        broken_kwargs = {**condition_kwargs, "expression": "report.category ==="}
        with pytest.raises(ValidationError, match="does not parse"):
            PipeConditionBlueprint.model_validate(broken_kwargs)

        parsed_sources = _counting_parses(mocker=mocker)
        with trusting_authored_templates():
            PipeConditionBlueprint.model_validate(broken_kwargs)
            PipeConditionBlueprint.model_validate({**condition_kwargs, "expression": "report.category"})
        assert not parsed_sources
