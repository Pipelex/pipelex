"""What a kernel judgment call hands back, for a judgment asking one question and for one asking several.

Four intermediates ride along because the kernel is where they are produced and the interpreter's
execution-graph tracer records them: the assembled evidence prompt, the rendered question, the
`JudgmentSetting` *after* handle resolution, and the judging model's raw answer, which carries a
distribution the verdict native's rendering does not show. The memory contract holds as everywhere
else: **the returned `memory` is the result**.

The serialization note on `pipelex.kernel.llm_results` applies here too — `content` is annotated with
the base `StuffContent`, so use `kajson` rather than a plain `model_dump()`.
"""

from pydantic import BaseModel, ConfigDict

from pipelex.cogt.judgment.judgment_models import JudgmentAnswer, JudgmentOutcome, JudgmentPrompt
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import StuffContent


class JudgmentResult(BaseModel):
    """The outcome of a kernel judgment call.

    `content` is the verdict native the answer translates to: a `YesNoContent`, a `ChoiceContent` or
    a `RatingContent`. `prompt` is the evidence as the model was given it: the rendered text and the
    files its tokens number. `threshold_applied` says what became of a declared threshold: `True` when it
    decided a yes/no verdict from the reported probability, `False` when the judging model reported no
    probability on a live run and its own verdict stood, and `None` when no threshold was declared or
    the run was dry.
    """

    model_config = ConfigDict(frozen=True)

    memory: WorkingMemory
    content: StuffContent
    prompt: JudgmentPrompt
    rendered_question: str
    judgment_setting: JudgmentSetting
    answer: JudgmentAnswer
    threshold_applied: bool | None = None


class QuestionJudgment(BaseModel):
    """What became of one question of a judgment asking several.

    `rendered_question` is the question as the model was asked it. `outcome` is the judging model's raw
    outcome: an answer, which carries a distribution the verdict native's rendering does not show, or a
    refusal, which left the question's field absent. `threshold_applied` reads as `JudgmentResult`'s does
    for this question, and is `None` for a refusal.
    """

    model_config = ConfigDict(frozen=True)

    rendered_question: str
    outcome: JudgmentOutcome
    threshold_applied: bool | None = None


class MultiJudgmentResult(BaseModel):
    """The outcome of a kernel judgment call asking several questions over one evidence.

    `content` is the output structure, holding the verdict native of each question in the field of its
    name, a refused question's optional field left absent. `prompt` is the evidence as the model was
    given it, and `judgments` says, by question name, what each question was asked as and what the model
    answered, refusals included.
    """

    model_config = ConfigDict(frozen=True)

    memory: WorkingMemory
    content: StuffContent
    prompt: JudgmentPrompt
    judgment_setting: JudgmentSetting
    judgments: dict[str, QuestionJudgment]
