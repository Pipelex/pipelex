"""PipeJudgeSpec.rendered_pretty shows what the author wrote, markup characters included."""

from rich.console import Console

from pipelex.builder.pipe.pipe_judge_spec import PipeJudgeSpec


class TestPipeJudgeSpecRendering:
    def test_a_bracketed_word_in_the_question_is_shown_as_written(self) -> None:
        spec = PipeJudgeSpec(
            pipe_code="is_flagged",
            description="Judge the flag",
            inputs={"message": "Text"},
            output="YesNo",
            question="Is the [urgent] flag set, or the [/x] one?",
        )
        console = Console(record=True, width=120)

        console.print(spec.rendered_pretty())

        assert "Is the [urgent] flag set, or the [/x] one?" in console.export_text()
