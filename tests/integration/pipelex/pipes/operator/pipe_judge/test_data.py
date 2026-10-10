import json
from typing import Any, ClassVar

from pydantic import Field

from pipelex.core.stuffs.choice_content import ChoiceContent
from pipelex.core.stuffs.rating_content import RatingContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.yes_no_content import YesNoContent


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


class PipeJudgeSeveralQuestionsTestData:
    """A bundle with one PipeJudge step asking several questions, built from its output's structure and its question tables."""

    PIPE_CODE = "judge_it"
    MESSAGE = "Every payment page has shown an error since this morning, and we cannot take any order."

    # The output's fields: a required yes/no, a required choice refined by `Team`, and an optional rating.
    STRUCTURE: ClassVar[dict[str, str]] = {
        "urgent": '{ type = "concept", concept_ref = "YesNo", description = "Whether the message is urgent", required = true }',
        "team": '{ type = "concept", concept_ref = "Team", description = "The team that handles it", required = true }',
        "severity": '{ type = "concept", concept_ref = "Rating", description = "How severe the reported issue is" }',
    }

    QUESTIONS: ClassVar[dict[str, str]] = {
        "urgent": 'question = "Is the message urgent?"\nthreshold = 0.7\ncriteria = { yes = "It cannot wait", no = "It can wait" }',
        "team": 'question = "Which team handles it?"\noptions = { billing = "Charges and invoices", technical = "Errors and outages" }',
        "severity": 'question = "How severe is the reported issue?"\nlevels = [{ label = "Minor" }, { label = "Major" }]',
    }

    @classmethod
    def bundle(
        cls,
        *,
        structure: dict[str, str] | None = None,
        questions: dict[str, str] | None = None,
        output: str = "Triage",
        inputs: str = '{ message = "Text" }',
        prompt: str = "@message",
        extra_concepts: str = "",
    ) -> str:
        """The step's output structure and question tables as written, each field and question a TOML line or table body by name."""
        structure_lines = "\n".join(f"{name} = {field}" for name, field in (structure if structure is not None else cls.STRUCTURE).items())
        question_tables = "\n\n".join(
            f"[pipe.judge_it.questions.{name}]\n{table}" for name, table in (questions if questions is not None else cls.QUESTIONS).items()
        )
        return f"""
domain = "judge_several"
description = "Loading a PipeJudge step asking several questions"

[concept]
Team = {{ description = "The team a ticket goes to", refines = "Choice" }}
Note = "A note"
{extra_concepts}

[concept.Triage]
description = "What a triage of a message found"

[concept.Triage.structure]
{structure_lines}

[pipe.judge_it]
type = "PipeJudge"
description = "Judge the evidence"
inputs = {inputs}
output = "{output}"
model = "{PipeJudgeLoadTestData.JUDGMENT_MODEL}"
prompt = {json.dumps(prompt)}

{question_tables}
"""


class ClassBackedTriage(StructuredContent):
    """A hand-written structure class holding one verdict per question, the rating left optional."""

    urgent: YesNoContent = Field(description="Whether the message is urgent")
    team: ChoiceContent = Field(description="The team that handles it")
    severity: RatingContent | None = Field(default=None, description="How severe the reported issue is")


class ClassBackedOpenTriage(StructuredContent):
    """A hand-written structure class whose yes/no field is typed `Any`, which maps to no concept."""

    urgent: Any = Field(description="Whether the message is urgent")
    team: ChoiceContent = Field(description="The team that handles it")
    severity: RatingContent | None = Field(default=None, description="How severe the reported issue is")


class PipeJudgeClassBackedTestData:
    """A PipeJudge asking several questions into a concept whose structure is a registered Python class."""

    @classmethod
    def bundle(cls, *, structure_class_name: str) -> str:
        question_tables = "\n\n".join(
            f"[pipe.judge_it.questions.{name}]\n{table}" for name, table in PipeJudgeSeveralQuestionsTestData.QUESTIONS.items()
        )
        return f"""
domain = "judge_class_backed"
description = "A PipeJudge filling a class-backed structure"

[concept.Triage]
description = "What a triage of a message found"
structure = "{structure_class_name}"

[pipe.judge_it]
type = "PipeJudge"
description = "Judge the evidence"
inputs = {{ message = "Text" }}
output = "Triage"
model = "{PipeJudgeLoadTestData.JUDGMENT_MODEL}"
prompt = "@message"

{question_tables}
"""


class PipeJudgeOptionalFileTestData:
    """A PipeJudge whose evidence prompt reads an optional file, run with that file absent or present."""

    PIPE_CODE = "judge_damage"
    NOTE = "The parcel arrived with one corner crushed."
    PHOTO_URL = "https://example.com/parcel-corner.png"

    # (topic, the optional input's declaration, the evidence prompt reading it behind a guard)
    ABSENT_CASES: ClassVar[list[tuple[str, str, str]]] = [
        ("image", 'photo = "Image?"', "A claim note: $note\n@?photo\n"),
        ("document", 'claim = "Document?"', "A claim note: $note\n@?claim\n"),
        ("list_of_images", 'album = "Album?"', "A claim note: $note{% if album %}\nThe photos: $album.photos{% endif %}"),
    ]

    @classmethod
    def bundle(cls, *, optional_input: str, prompt: str) -> str:
        return f"""
domain = "judge_optional_files"
description = "A PipeJudge whose evidence may hold a file"

[concept.Album]
description = "Photos taken when a parcel was delivered"

[concept.Album.structure]
photos = {{ type = "list", item_type = "concept", item_concept_ref = "native.Image", description = "The photos", required = true }}

[pipe.{cls.PIPE_CODE}]
type = "PipeJudge"
description = "Judge whether a parcel's damage is serious"
inputs = {{ note = "Text", {optional_input} }}
output = "YesNo"
model = "{PipeJudgeLoadTestData.JUDGMENT_MODEL}"
prompt = {json.dumps(prompt)}
question = "Is the damage serious?"
"""
