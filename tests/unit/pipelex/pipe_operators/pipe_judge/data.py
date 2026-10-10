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


def _questions(**overrides: Any) -> dict[str, Any]:
    """Three questions of each kind about one message, with the given question tables on top: a table given as `None` is dropped."""
    questions: dict[str, Any] = {
        "urgent": {"question": "Is it urgent?", "threshold": 0.7, "criteria": {"yes": "It cannot wait", "no": "It can wait"}},
        "team": {"question": "Which team handles it?", "options": {"billing": "Charges and invoices", "technical": ""}},
        "severity": {"question": "How severe is it?", "levels": [{"label": "Low"}, {"label": "High"}]},
    }
    questions.update(overrides)
    return {key: value for key, value in questions.items() if value is not None}


def _multi(**fields: Any) -> dict[str, Any]:
    """A PipeJudge blueprint asking several questions over the evidence of one message, with the given fields on top.

    A field given as `None` is left out, so `_multi(question=…)` adds a single-form question beside the several.
    """
    blueprint: dict[str, Any] = {
        "description": "d",
        "inputs": {"message": "Text"},
        "output": "MessageTriage",
        "prompt": "A message from a customer:\n@message",
        "questions": _questions(),
    }
    blueprint.update(fields)
    return {key: value for key, value in blueprint.items() if value is not None}


def _one_question(**question_fields: Any) -> dict[str, Any]:
    """A PipeJudge blueprint asking one question through `questions`, the question table being the given fields."""
    return _multi(questions={"verdict": question_fields})


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

    # Several questions: (test_id, blueprint fields, a fragment of its message).
    REFUSED_SEVERAL: ClassVar[list[tuple[str, dict[str, Any], str]]] = [
        ("question_and_questions", _multi(question="Is it urgent?"), "sets both `question` and `questions`"),
        ("neither_question_nor_questions", _multi(questions=None), "or several in `questions`"),
        ("no_question_in_questions", _multi(questions={}), "`questions` holds at least one question, and this one holds none"),
        ("key_not_an_identifier", _multi(questions=_questions(**{"is-urgent": {"question": "Urgent?"}})), "'is-urgent' is not"),
        ("key_a_python_keyword", _multi(questions=_questions(**{"class": {"question": "Urgent?"}})), "'class' is not"),
        ("key_starting_with_an_underscore", _multi(questions=_questions(_urgent={"question": "Urgent?"})), "'_urgent' is not"),
        ("key_a_reserved_name", _multi(questions=_questions(model_config={"question": "Urgent?"})), "'model_config' is not"),
        ("options_on_the_pipe", _multi(options={"a": "", "b": ""}), "sets `options` on each question rather than on the pipe"),
        ("levels_on_the_pipe", _multi(levels=["low", "high"]), "sets `levels` on each question rather than on the pipe"),
        ("criteria_on_the_pipe", _multi(criteria={"yes": "y", "no": "n"}), "sets `criteria` on each question rather than on the pipe"),
        ("threshold_on_the_pipe", _multi(threshold=0.7), "sets `threshold` on each question rather than on the pipe"),
        ("question_table_without_question", _one_question(threshold=0.7), "writes what it asks in `question`, and this one sets none"),
        ("empty_question_in_a_table", _one_question(question=""), "its `question` cannot be empty"),
        ("blank_question_in_a_table", _one_question(question="  \n "), "its `question` cannot be empty"),
        ("prompt_in_a_question_table", _one_question(question="Is it urgent?", prompt="@message"), "prompt"),
        ("question_with_options_and_levels", _one_question(question="Q?", options={"a": "", "b": ""}, levels=["low", "high"]), "not both"),
        (
            "criteria_beside_options_in_a_question",
            _one_question(question="Q?", options={"a": "", "b": ""}, criteria={"yes": "y", "no": "n"}),
            "`criteria` applies to a yes/no question only, and this question declares `options`",
        ),
        ("question_threshold_out_of_range", _one_question(question="Q?", threshold=1.5), "strictly between 0 and 1, and this question declares 1.5"),
        ("question_with_one_option", _one_question(question="Q?", options={"only": ""}), "at least two `options`"),
        ("question_with_one_level", _one_question(question="Q?", levels=["only"]), "at least two `levels`"),
        ("question_with_a_lone_criterion", _one_question(question="Q?", criteria={"yes": "y"}), "these declare `yes` without `no`"),
        (
            "question_with_mixed_labels",
            _one_question(question="Q?", levels=[{"label": "Low"}, "High"]),
            "every level carries a `label` or none does",
        ),
        (
            "undeclared_variable_in_a_question",
            _multi(questions=_questions(urgent={"question": "Is it about $topic?"})),
            "Variable 'topic' is read by the prompt or questions",
        ),
        (
            "input_no_template_reads",
            _multi(inputs={"message": "Text", "history": "Text"}),
            "Input 'history' is declared but never read by the prompt or questions",
        ),
        ("output_with_brackets", _multi(output="MessageTriage[]"), "fills one structure with their verdicts"),
    ]

    # A field written as null holds no value, so it neither sets a form nor clashes with the other one.
    REFUSED_NULLS: ClassVar[list[tuple[str, dict[str, Any], str]]] = [
        ("null_question_alone", {**_judge(), "question": None}, "the question is written in `question`, or several in `questions`"),
        ("null_question_and_null_questions", {**_judge(), "question": None, "questions": None}, "or several in `questions`"),
        ("null_question_in_a_question_table", _one_question(question=None), "writes what it asks in `question`, and this one sets none"),
        ("null_prompt", {**_judge(), "prompt": None}, "judges the evidence its `prompt` presents, and this one sets no `prompt`"),
    ]

    ACCEPTED_NULLS: ClassVar[list[tuple[str, dict[str, Any]]]] = [
        ("question_beside_null_questions", {**_judge(), "questions": None}),
        ("questions_beside_null_question", {**_multi(), "question": None}),
    ]

    # Both forms, with every field a blueprint may carry, to round-trip through a dump.
    ROUND_TRIPS: ClassVar[list[tuple[str, dict[str, Any]]]] = [
        ("single_yes_no", _judge(model="@default-judgment", threshold=0.8, criteria={"yes": "Today", "no": "Later"})),
        ("single_rating", _judge(output="Rating", levels=[{"label": "Low", "description": "Barely"}, {"label": "High"}])),
        ("single_choice", _judge(output="Choice", options={"billing": "", "technical": "Errors"})),
        ("several", _multi(model="@default-judgment")),
    ]

    # Several questions: (test_id, blueprint fields, the kind each question resolves to).
    ACCEPTED_SEVERAL: ClassVar[list[tuple[str, dict[str, Any], dict[str, JudgmentKind]]]] = [
        (
            "one_question_of_each_kind",
            _multi(),
            {"urgent": JudgmentKind.YES_NO, "team": JudgmentKind.CHOICE, "severity": JudgmentKind.RATING},
        ),
        ("a_single_question_in_questions", _one_question(question="Is it urgent?"), {"verdict": JudgmentKind.YES_NO}),
        (
            "an_input_read_by_one_question_alone",
            _multi(inputs={"message": "Text", "topic": "Text"}, questions=_questions(urgent={"question": "Is it about $topic?"})),
            {"urgent": JudgmentKind.YES_NO, "team": JudgmentKind.CHOICE, "severity": JudgmentKind.RATING},
        ),
    ]
