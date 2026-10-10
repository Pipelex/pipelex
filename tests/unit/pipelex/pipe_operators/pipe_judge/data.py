from typing import Any, ClassVar

from pipelex.cogt.judgment.judgment_models import JudgmentKind


def _judge(**fields: Any) -> dict[str, Any]:
    """A PipeJudge blueprint's fields: a yes/no question over the evidence of one message, with the given fields on top.

    A field given as `None` is left out, which is how a case drops one of the defaults.
    """
    blueprint: dict[str, Any] = {
        "description": "d",
        "inputs": {"message": "Text"},
        "output": "YesNo",
        "prompt": "A message from a customer:\n@message",
        "question": "Is it urgent?",
    }
    blueprint.update(fields)
    return {key: value for key, value in blueprint.items() if value is not None}


class PipeJudgeBlueprintTestCases:
    """Each refusal is (test_id, blueprint fields, a fragment of its message); each acceptance is (test_id, fields, the kind it resolves to)."""

    REFUSED: ClassVar[list[tuple[str, dict[str, Any], str]]] = [
        (
            "prompt_as_the_question",
            _judge(question=None, prompt="Is the message urgent?"),
            "`prompt` holds the evidence the question is asked over, and the question is written in `question`",
        ),
        ("no_question_at_all", _judge(question=None), "the question is written in `question`"),
        ("no_prompt", _judge(prompt=None), "judges the evidence its `prompt` presents, and this one sets no `prompt`"),
        ("empty_prompt", _judge(prompt=""), "`prompt` cannot be empty"),
        ("blank_prompt", _judge(prompt="  \n "), "`prompt` cannot be empty"),
        ("empty_question", _judge(question=""), "`question` cannot be empty"),
        ("blank_question", _judge(question="  \n "), "`question` cannot be empty"),
        ("dotted_input", _judge(inputs={"invoice.total": "Number"}), "Input 'invoice.total' is not a plain input name"),
        ("options_and_levels", _judge(output="Choice", options={"a": "", "b": ""}, levels=["low", "high"]), "not both"),
        (
            "criteria_beside_options",
            _judge(output="Choice", options={"a": "", "b": ""}, criteria={"yes": "y", "no": "n"}),
            "`criteria` applies to a yes/no question only",
        ),
        ("threshold_beside_levels", _judge(output="Rating", levels=["low", "high"], threshold=0.7), "`threshold` applies to a yes/no question only"),
        ("one_option", _judge(output="Choice", options={"only": "the one"}), "at least two `options`"),
        ("empty_option_key", _judge(output="Choice", options={"": "nothing", "b": ""}), "none may be empty"),
        ("one_level", _judge(output="Rating", levels=["only"]), "at least two `levels`"),
        ("empty_level", _judge(output="Rating", levels=["low", "  "]), "level 1 is"),
        ("empty_level_table", _judge(output="Rating", levels=["low", {}]), "carries a `label`, a `description` or both"),
        ("blank_level_label", _judge(output="Rating", levels=[{"label": "Low"}, {"label": " ", "description": "High"}]), "level 1"),
        ("unknown_level_key", _judge(output="Rating", levels=[{"label": "Low"}, {"label": "High", "score": 3}]), "score"),
        (
            "labels_mixed_with_unlabelled_levels",
            _judge(output="Rating", levels=[{"label": "Low", "description": "Barely"}, "Severe"]),
            "every level carries a `label` or none does",
        ),
        (
            "duplicated_labels",
            _judge(output="Rating", levels=[{"label": "Low"}, {"label": "High"}, {"label": "Low"}]),
            "the labels of one scale are distinct, and 'Low' is repeated",
        ),
        ("threshold_zero", _judge(threshold=0), "strictly between 0 and 1"),
        ("threshold_one", _judge(threshold=1), "strictly between 0 and 1"),
        ("unknown_criteria_key", _judge(criteria={"yes": "y", "no": "n", "maybe": "m"}), "maybe"),
        (
            "criteria_yes_alone",
            _judge(criteria={"yes": "The customer needs an answer today"}),
            "Criteria describe both answers, and these declare `yes` without `no`: write `no` as the complement of `yes`",
        ),
        (
            "criteria_no_alone",
            _judge(criteria={"no": "The message can wait"}),
            "Criteria describe both answers, and these declare `no` without `yes`: write `yes` as the complement of `no`",
        ),
        (
            "criteria_empty_table",
            _judge(criteria={}),
            "Criteria describe both answers, and this table declares neither: write both `yes` and `no`, or remove the table",
        ),
        ("criteria_empty_side", _judge(criteria={"yes": "Today", "no": " "}), "`no` cannot be empty"),
        ("output_with_brackets", _judge(output="YesNo[]"), "produces one verdict"),
        ("undeclared_variable_in_question", _judge(question="Is it about $topic?"), "Variable 'topic' is read by the prompt or question"),
        ("undeclared_variable_in_prompt", _judge(prompt="@message\nFrom: $sender"), "Variable 'sender' is read by the prompt or question"),
        (
            "unread_input",
            _judge(inputs={"message": "Text", "history": "Text"}),
            "Input 'history' is declared but never read by the prompt or question",
        ),
    ]

    ACCEPTED: ClassVar[list[tuple[str, dict[str, Any], JudgmentKind]]] = [
        ("yes_no_with_both_criteria", _judge(threshold=0.8, criteria={"yes": "needs an answer today", "no": "can wait"}), JudgmentKind.YES_NO),
        (
            "input_read_by_the_question_alone",
            _judge(inputs={"message": "Text", "topic": "Text"}, question="Is it about $topic?"),
            JudgmentKind.YES_NO,
        ),
        ("empty_string_option_description", _judge(output="Choice", options={"billing": "", "technical": "Bugs"}), JudgmentKind.CHOICE),
        ("rating_described_by_strings", _judge(output="Rating", levels=["cosmetic", "a workaround exists", "blocking"]), JudgmentKind.RATING),
        (
            "rating_labelled_and_described",
            _judge(
                output="Rating",
                levels=[
                    {"label": "Cosmetic", "description": "Appearance only"},
                    {"label": "Workaround available"},
                    {"label": "Fully blocked", "description": "A task fails with no workaround"},
                ],
            ),
            JudgmentKind.RATING,
        ),
        ("rating_unlabelled_tables_and_strings", _judge(output="Rating", levels=[{"description": "Barely"}, "Severe"]), JudgmentKind.RATING),
    ]
