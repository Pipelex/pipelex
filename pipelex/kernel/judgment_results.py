"""What a kernel judgment call hands back.

Three intermediates ride along because the kernel is where they are produced and the interpreter's
execution-graph tracer records them: the rendered question, the `JudgmentSetting` *after* handle
resolution, and the judging model's raw answer, which carries a distribution the verdict native's
rendering does not show. The memory contract holds as everywhere else: **the returned `memory` is the
result**.

The serialization note on `pipelex.kernel.llm_results` applies here too — `content` is annotated with
the base `StuffContent`, so use `kajson` rather than a plain `model_dump()`.
"""

from pydantic import BaseModel, ConfigDict

from pipelex.cogt.judgment.judgment_models import JudgmentAnswer
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import StuffContent


class JudgmentResult(BaseModel):
    """The outcome of a kernel judgment call.

    `content` is the verdict native the answer translates to: a `YesNoContent`, a `ChoiceContent` or
    a `RatingContent`. `threshold_applied` says what became of a declared threshold: `True` when it
    decided a yes/no verdict from the reported probability, `False` when the judging model reported no
    probability on a live run and its own verdict stood, and `None` when no threshold was declared or
    the run was dry.
    """

    model_config = ConfigDict(frozen=True)

    memory: WorkingMemory
    content: StuffContent
    rendered_question: str
    judgment_setting: JudgmentSetting
    answer: JudgmentAnswer
    threshold_applied: bool | None = None
