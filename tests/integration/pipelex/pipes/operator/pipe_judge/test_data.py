import json
from typing import ClassVar


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
