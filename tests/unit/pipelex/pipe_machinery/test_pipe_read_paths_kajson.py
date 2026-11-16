from typing import Any, Callable

from kajson import kajson
from pytest_mock import MockerFixture

from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.interpreter_hub import get_concept_library
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.llm.llm_prompt_blueprint import LLMPromptBlueprint
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.tools.jinja2 import jinja2_required_variables as jinja2_required_variables_module
from pipelex.tools.jinja2.template_category import TemplateCategory

_DOMAIN_CODE = "read_paths_domain"
_READ_PATH_KEYS = ("template_read_paths", "expression_read_paths")


def _roundtrip(value: Any) -> Any:
    serialized = kajson.dumps(value)  # pyright: ignore[reportUnknownMemberType]
    return kajson.loads(serialized)  # pyright: ignore[reportUnknownMemberType]


def _assert_no_read_path_key(dumped: dict[str, Any]) -> None:
    for read_path_key in _READ_PATH_KEYS:
        assert read_path_key not in dumped


class TestPipeReadPathsKajson:
    """A pipe whose read paths were computed, as bundle validation computes them, still crosses a host boundary.

    kajson, the encoding a host runtime's data converter uses, encodes a pydantic model from its instance `__dict__`,
    so a read path cached there would travel with the pipe, and a frozenset does not encode at all.
    """

    def test_llm_prompt_blueprint_roundtrips_after_its_read_paths_were_computed(self) -> None:
        blueprint = LLMPromptBlueprint(
            system_prompt_blueprint=TemplateBlueprint(template="You know about {{ field.name }}", category=TemplateCategory.LLM_PROMPT),
            prompt_blueprint=TemplateBlueprint(template="Describe $topic", category=TemplateCategory.LLM_PROMPT),
        )
        assert blueprint.template_read_paths == frozenset({"topic", "field.name"})

        roundtripped = _roundtrip(blueprint)

        assert isinstance(roundtripped, LLMPromptBlueprint)
        assert roundtripped == blueprint
        assert roundtripped.template_read_paths == frozenset({"topic", "field.name"})
        assert blueprint.required_variables() == {"topic", "field"}
        _assert_no_read_path_key(blueprint.model_dump())

    def test_validated_pipe_llm_roundtrips(self, load_empty_library: Callable[[], str]) -> None:
        load_empty_library()
        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=_DOMAIN_CODE,
            pipe_code="describe_topic",
            blueprint=PipeLLMBlueprint(
                type="PipeLLM",
                description="Describe a topic",
                inputs={"topic": "native.Text"},
                output="native.Text",
                prompt="Describe $topic",
            ),
        )
        assert pipe_llm.required_variables() == {"topic"}
        assert pipe_llm.llm_prompt_spec.template_read_paths == frozenset({"topic"})

        roundtripped = _roundtrip(pipe_llm)

        assert isinstance(roundtripped, PipeLLM)
        assert roundtripped == pipe_llm
        assert roundtripped.required_variables() == {"topic"}
        dumped = pipe_llm.model_dump()
        _assert_no_read_path_key(dumped)
        _assert_no_read_path_key(dumped["llm_prompt_spec"])

    def test_validated_pipe_condition_roundtrips(self, load_empty_library: Callable[[], str]) -> None:
        load_empty_library()
        get_concept_library().add_concepts(
            concepts=[
                ConceptFactory.make_from_blueprint(
                    domain_code=_DOMAIN_CODE,
                    concept_code="Ticket",
                    blueprint_or_string_description=ConceptBlueprint(description="A ticket"),
                )
            ]
        )
        pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=_DOMAIN_CODE,
            pipe_code="route_ticket",
            concept_codes_from_the_same_domain=["Ticket"],
            blueprint=PipeConditionBlueprint(
                description="Route a ticket by its status",
                inputs={"ticket": "Ticket"},
                output="native.Text?",
                expression="ticket.status",
                outcomes={"open": SpecialOutcome.CONTINUE},
                default_outcome=SpecialOutcome.CONTINUE,
            ),
        )
        assert pipe_condition.expression_read_paths == frozenset({"ticket.status"})

        roundtripped = _roundtrip(pipe_condition)

        assert isinstance(roundtripped, PipeCondition)
        assert roundtripped == pipe_condition
        assert roundtripped.expression_read_paths == frozenset({"ticket.status"})
        _assert_no_read_path_key(pipe_condition.model_dump())

    def test_read_paths_are_parsed_once_per_template_and_never_held_on_the_pipe(self, mocker: MockerFixture) -> None:
        """Validation and every step read a pipe's read paths, so each template is parsed once, and a copy that crossed
        a boundary reads the same parse.
        """
        parse_spy = mocker.spy(jinja2_required_variables_module, "detect_jinja2_read_paths")
        blueprint = LLMPromptBlueprint(
            prompt_blueprint=TemplateBlueprint(template="Summarize {{ once_parsed_report.summary_section }}", category=TemplateCategory.LLM_PROMPT),
        )

        for _ in range(3):
            assert blueprint.template_read_paths == frozenset({"once_parsed_report.summary_section"})
            assert blueprint.required_variables() == {"once_parsed_report"}
            assert blueprint.to_prompt_content().read_paths == frozenset({"once_parsed_report.summary_section"})
        roundtripped = _roundtrip(blueprint)
        assert roundtripped.template_read_paths == frozenset({"once_parsed_report.summary_section"})

        assert parse_spy.call_count == 1
        _assert_no_read_path_key(vars(blueprint))
