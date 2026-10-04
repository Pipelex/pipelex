from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, field_validator, model_validator
from typing_extensions import override

from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.pipe_operators.judge.pipe_judge_blueprint import JudgeYesNoCriteria, PipeJudgeBlueprint, read_prompt_as_question
from pipelex.tools.misc.pretty import require_rich_for_rendering

if TYPE_CHECKING:
    from pipelex.tools.misc.pretty import PrettyPrintable


class PipeJudgeSpec(PipeSpec):
    """Specs for judgment pipe operations in the Pipelex framework.

    PipeJudge asks a judging model one closed question about its inputs. Declare `options` for a
    choice, `levels` for a rating, or neither for a yes/no question, which may carry `criteria` and a
    `threshold`. Every input is material to judge, so the question need not name them.
    """

    type: Literal["PipeJudge"] = "PipeJudge"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    model: str | None = Field(
        default=None,
        description="Judgment model preset, alias, waterfall, or direct model handle. Use presets from 'pipelex-agent models'.",
    )
    question: str = Field(
        description="The one closed question to ask about the inputs: use `$` prefix for an inline parameter (e.g., `Is it about $topic?`).",
    )
    options: dict[str, str] | None = Field(
        default=None,
        description="For a choice question: each key is an option, each value describes it as a concrete situation (an empty string for none).",
    )
    levels: list[str] | None = Field(
        default=None,
        description="For a rating question: the levels from lowest to highest, each describing a situation rather than a degree.",
    )
    criteria: JudgeYesNoCriteria | None = Field(default=None, description="For a yes/no question: what a yes and what a no mean.")
    threshold: float | None = Field(
        default=None,
        description="For a yes/no question: the probability of yes at or above which the verdict is yes, strictly between 0 and 1.",
    )

    @field_validator("model", mode="before")
    @classmethod
    def reject_empty_model(cls, value: str | None) -> str | None:
        if isinstance(value, str) and not value.strip():
            msg = "Model cannot be an empty string; omit the field to use defaults"
            raise ValueError(msg)
        return value

    @model_validator(mode="before")
    @classmethod
    def read_prompt_synonym(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Accept `prompt` for `question`, the spelling every other inference operator uses, as the blueprint does."""
        return read_prompt_as_question(values=values)

    @override
    def rendered_pretty(self, *, title: str | None = None, depth: int = 0) -> "PrettyPrintable":
        require_rich_for_rendering()
        from rich.console import Group
        from rich.markup import escape
        from rich.panel import Panel
        from rich.text import Text

        judge_group = Group()
        judge_group.renderables.append(super().rendered_pretty(title=title, depth=depth))
        judge_group.renderables.append(Text())
        judge_group.renderables.append(Text.from_markup(f"Model: [bold yellow]{escape(self.model or '(default)')}[/bold yellow]"))
        judge_group.renderables.append(Text())
        judge_group.renderables.append(Panel(Text(self.question), title="Question", title_align="left", border_style="cyan", padding=(0, 1)))
        detail_lines: list[str] = []
        if self.options is not None:
            detail_lines.extend(f"Option {key}: {description}" if description else f"Option {key}" for key, description in self.options.items())
        if self.levels is not None:
            detail_lines.extend(f"Level {index}: {level}" for index, level in enumerate(self.levels))
        if self.criteria is not None:
            if self.criteria.yes is not None:
                detail_lines.append(f"Yes means: {self.criteria.yes}")
            if self.criteria.no is not None:
                detail_lines.append(f"No means: {self.criteria.no}")
        if self.threshold is not None:
            detail_lines.append(f"Threshold: {self.threshold}")
        if detail_lines:
            judge_group.renderables.append(Text())
            for detail_line in detail_lines:
                judge_group.renderables.append(Text(detail_line, style="dim"))
        return judge_group

    @override
    def to_blueprint(self) -> PipeJudgeBlueprint:
        """Convert this PipeJudgeSpec to the core PipeJudgeBlueprint."""
        base_blueprint = super().to_blueprint()
        return PipeJudgeBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs_concept_specs,
            output=base_blueprint.output,
            question=self.question,
            model=self.model,
            options=self.options,
            levels=self.levels,
            criteria=self.criteria,
            threshold=self.threshold,
        )
