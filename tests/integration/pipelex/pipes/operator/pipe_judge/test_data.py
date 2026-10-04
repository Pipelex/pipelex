class PipeJudgeLoadTestData:
    """A bundle with one PipeJudge step, built from the step's own fields."""

    JUDGMENT_MODEL = "jev-1.13.0"

    @classmethod
    def bundle(cls, *, inputs: str = '{ message = "Text" }', output: str = "YesNo", step_fields: str = "") -> str:
        return f"""
domain = "judge_load"
description = "Loading a PipeJudge step"

[concept]
Team = {{ description = "The team a ticket goes to", refines = "Choice" }}
Ticket = "A support ticket"

[pipe.judge_it]
type = "PipeJudge"
description = "Judge the material"
inputs = {inputs}
output = "{output}"
question = "Is it urgent?"
{step_fields}
"""
