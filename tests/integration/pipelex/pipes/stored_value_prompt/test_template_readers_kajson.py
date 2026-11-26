from pathlib import Path
from typing import Any, Callable

import pytest
from kajson import kajson

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.pipe_operators.img_gen.pipe_img_gen import PipeImgGen
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.pipe_operators.judge.pipe_judge import PipeJudge
from pipelex.pipe_operators.judge.pipe_judge_blueprint import JudgeQuestionBlueprint, PipeJudgeBlueprint
from pipelex.pipe_operators.search.pipe_search import PipeSearch
from pipelex.pipe_operators.search.pipe_search_blueprint import PipeSearchBlueprint
from tests.integration.pipelex.pipes.operator.pipe_judge.cases import PipeJudgeLoadCases

_BUNDLES_DIR = Path("tests/integration/pipelex/pipes/stored_value_prompt/bundles")
_TEXT_INPUTS = {"subject": NativeConceptCode.TEXT, "pages": NativeConceptCode.TEXT}


def _read_paths_of(pipe: PipeAbstract) -> frozenset[str]:
    """The read paths the pipe computes once and loads by before it renders."""
    if isinstance(pipe, PipeImgGen):
        return pipe.img_gen_prompt_blueprint.template_read_paths
    if isinstance(pipe, PipeSearch):
        return pipe.prompt_read_paths
    if isinstance(pipe, (PipeJudge, PipeCompose)):
        return pipe.template_read_paths
    msg = f"No read paths known for {type(pipe).__name__}"
    raise AssertionError(msg)


def _make_pipe(*, kind: str) -> PipeAbstract:
    match kind:
        case "img_gen":
            return PipeFactory[PipeImgGen].make_from_blueprint(
                domain_code="stored_value_readers",
                pipe_code="paint_the_pages",
                blueprint=PipeImgGenBlueprint(
                    description="Paint pages",
                    inputs=_TEXT_INPUTS,
                    output=NativeConceptCode.IMAGE,
                    prompt="Paint {{ subject.text }}",
                    negative_prompt="Nothing of {{ pages.text }}",
                ),
            )
        case "search":
            return PipeFactory[PipeSearch].make_from_blueprint(
                domain_code="stored_value_readers",
                pipe_code="search_the_pages",
                blueprint=PipeSearchBlueprint(
                    description="Search pages",
                    inputs=_TEXT_INPUTS,
                    output=NativeConceptCode.SEARCH_RESULT,
                    prompt="Find {{ subject.text }} in {{ pages.text }}",
                ),
            )
        case "judge":
            return PipeFactory[PipeJudge].make_from_blueprint(
                domain_code="stored_value_readers",
                pipe_code="judge_the_pages",
                blueprint=PipeJudgeBlueprint(
                    description="Judge pages",
                    inputs=_TEXT_INPUTS,
                    output="PagesVerdicts",
                    prompt="The subject: {{ subject.text }}",
                    questions={
                        "is_long": JudgeQuestionBlueprint(question="Do these pages run long: {{ pages.text }}?"),
                        "is_about": JudgeQuestionBlueprint(question="Is it about {{ subject.text }}?"),
                    },
                    model=PipeJudgeLoadCases.JUDGMENT_MODEL,
                ),
                concept_codes_from_the_same_domain=["PagesVerdicts"],
            )
        case "compose_template":
            return PipeFactory[PipeCompose].make_from_blueprint(
                domain_code="stored_value_readers",
                pipe_code="compose_the_pages",
                blueprint=PipeComposeBlueprint(
                    description="Compose pages", inputs=_TEXT_INPUTS, output=NativeConceptCode.TEXT, template="{{ subject.text }}: {{ pages.text }}"
                ),
            )
        case "compose_construct":
            construct_fields: dict[str, Any] = {
                "description": "Compose a digest of pages",
                "inputs": _TEXT_INPUTS,
                "output": "PagesDigest",
                "construct": {"heading": {"template": "On {{ subject.text }}"}, "body": {"template": "{{ pages.text }}"}},
            }
            return PipeFactory[PipeCompose].make_from_blueprint(
                domain_code="stored_value_readers",
                pipe_code="compose_the_digest",
                blueprint=PipeComposeBlueprint.model_validate(construct_fields),
                concept_codes_from_the_same_domain=["PagesDigest"],
            )
        case _:
            msg = f"Unknown pipe kind '{kind}'"
            raise AssertionError(msg)


class TestTemplateReadersKajson:
    @pytest.mark.parametrize("kind", ["img_gen", "search", "judge", "compose_template", "compose_construct"])
    def test_a_pipe_whose_read_paths_were_computed_round_trips_through_kajson(
        self,
        load_test_library: Callable[[list[Path]], None],
        kind: str,
    ) -> None:
        """A pipe whose read paths were read still encodes as its fields alone, so a hosted job carrying it decodes an equal pipe.

        pydantic's equality compares private attributes too, so a read-path cache held on the pipe would make it unequal
        to its decoded copy: the paths are parsed once per template source in a process and held on no pipe.
        """
        load_test_library([_BUNDLES_DIR])
        pipe = _make_pipe(kind=kind)
        read_paths = _read_paths_of(pipe)
        assert read_paths >= {"subject.text", "pages.text"}

        serialized = kajson.dumps(pipe)  # pyright: ignore[reportUnknownMemberType]
        deserialized = kajson.loads(serialized)  # pyright: ignore[reportUnknownMemberType]

        assert isinstance(deserialized, type(pipe))
        assert deserialized == pipe
        assert deserialized.model_dump() == pipe.model_dump()
        assert _read_paths_of(deserialized) == read_paths
