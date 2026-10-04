from typing import Any, ClassVar

from pipelex.cogt.judgment.judgment_models import JudgmentKind


def _judge(**fields: Any) -> dict[str, Any]:
    """A PipeJudge blueprint's fields: a yes/no question over one message, with the given fields on top."""
    blueprint: dict[str, Any] = {"description": "d", "inputs": {"message": "Text"}, "output": "YesNo", "question": "Is it urgent?"}
    blueprint.update(fields)
    return {key: value for key, value in blueprint.items() if value is not None}


class PipeJudgeBlueprintTestCases:
    """Each refusal is (test_id, blueprint fields, a fragment of its message); each acceptance is (test_id, fields, the kind it resolves to)."""

    REFUSED: ClassVar[list[tuple[str, dict[str, Any], str]]] = [
        ("both_spellings", _judge(prompt="Is it urgent?"), "sets `question`, or `prompt` as its synonym, but not both"),
        ("options_and_levels", _judge(output="Choice", options={"a": "", "b": ""}, levels=["low", "high"]), "not both"),
        (
            "criteria_beside_options",
            _judge(output="Choice", options={"a": "", "b": ""}, criteria={"yes": "y"}),
            "`criteria` applies to a yes/no question only",
        ),
        ("threshold_beside_levels", _judge(output="Rating", levels=["low", "high"], threshold=0.7), "`threshold` applies to a yes/no question only"),
        ("one_option", _judge(output="Choice", options={"only": "the one"}), "at least two `options`"),
        ("empty_option_key", _judge(output="Choice", options={"": "nothing", "b": ""}), "none may be empty"),
        ("one_level", _judge(output="Rating", levels=["only"]), "at least two `levels`"),
        ("empty_level", _judge(output="Rating", levels=["low", "  "]), "level 1 is"),
        ("threshold_zero", _judge(threshold=0), "strictly between 0 and 1"),
        ("threshold_one", _judge(threshold=1), "strictly between 0 and 1"),
        ("unknown_criteria_key", _judge(criteria={"yes": "y", "maybe": "m"}), "maybe"),
        ("output_with_brackets", _judge(output="YesNo[]"), "produces one verdict"),
        ("undeclared_variable", _judge(question="Is $message about $topic?"), "Variable 'topic' is read by the question but not declared"),
    ]

    ACCEPTED: ClassVar[list[tuple[str, dict[str, Any], JudgmentKind]]] = [
        ("question_yes_no", _judge(threshold=0.8, criteria={"yes": "needs an answer today", "no": "can wait"}), JudgmentKind.YES_NO),
        ("prompt_alone", {**_judge(question=None), "prompt": "Is it urgent?"}, JudgmentKind.YES_NO),
        ("unreferenced_input", _judge(inputs={"message": "Text", "history": "Text"}, question="Is $message urgent?"), JudgmentKind.YES_NO),
        ("empty_string_option_description", _judge(output="Choice", options={"billing": "", "technical": "Bugs"}), JudgmentKind.CHOICE),
        ("rating", _judge(output="Rating", levels=["cosmetic", "a workaround exists", "blocking"]), JudgmentKind.RATING),
    ]
