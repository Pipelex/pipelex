import json


class PipeJudgeLoadTestData:
    """A bundle with one PipeJudge step, built from the step's own fields."""

    JUDGMENT_MODEL = "jev-1.13.0"

    @classmethod
    def bundle(
        cls,
        *,
        inputs: str = '{ message = "Text" }',
        output: str = "YesNo",
        prompt: str | None = "@message",
        question: str | None = "Is it urgent?",
        step_fields: str = "",
    ) -> str:
        """The step's fields as written: a `prompt` or a `question` given as `None` is left out of the table.

        A JSON string is a TOML basic string, escapes included, so the two templates are written that way.
        """
        prompt_line = f"prompt = {json.dumps(prompt)}" if prompt is not None else ""
        question_line = f"question = {json.dumps(question)}" if question is not None else ""
        return f"""
domain = "judge_load"
description = "Loading a PipeJudge step"

[concept]
Team = {{ description = "The team a ticket goes to", refines = "Choice" }}
Ticket = "A support ticket"

[pipe.judge_it]
type = "PipeJudge"
description = "Judge the evidence"
inputs = {inputs}
output = "{output}"
{prompt_line}
{question_line}
{step_fields}
"""
