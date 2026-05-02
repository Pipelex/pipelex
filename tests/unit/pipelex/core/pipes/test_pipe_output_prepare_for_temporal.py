from pytest_mock import MockerFixture

from pipelex.core.concepts.concept import Concept
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.text_content import TextContent


def _make_populated_pipe_output() -> PipeOutput:
    working_memory = WorkingMemory()
    working_memory.root["greeting"] = Stuff(
        stuff_code="test",
        stuff_name="greeting",
        concept=Concept(
            code="Text",
            domain_code=SpecialDomain.NATIVE,
            description="Plain text",
            structure_class_name="TextContent",
        ),
        content=TextContent(text="Hello!"),
    )
    return PipeOutput(working_memory=working_memory)


class TestPipeOutputPrepareForTemporal:
    def test_no_crate_returns_self_unchanged(self) -> None:
        pipe_output = _make_populated_pipe_output()

        result = pipe_output.prepare_for_temporal(library_crate=None)

        assert result is pipe_output
        assert result.working_memory_raw is None
        assert "greeting" in result.working_memory.root

    def test_with_crate_dehydrates(self, mocker: MockerFixture) -> None:
        from pipelex.libraries.library_crate import LibraryCrate  # noqa: PLC0415

        fake_crate = mocker.MagicMock(spec=LibraryCrate)
        pipe_output = _make_populated_pipe_output()

        result = pipe_output.prepare_for_temporal(library_crate=fake_crate)

        assert result is not pipe_output
        assert result.working_memory_raw is not None
        assert "greeting" in result.working_memory_raw.get("root", {})
        # Original is unchanged.
        assert pipe_output.working_memory_raw is None
        assert "greeting" in pipe_output.working_memory.root
        # The dehydrated copy has an empty WorkingMemory.
        assert not result.working_memory.root

    def test_with_crate_empty_wm_returns_self(self, mocker: MockerFixture) -> None:
        from pipelex.libraries.library_crate import LibraryCrate  # noqa: PLC0415

        fake_crate = mocker.MagicMock(spec=LibraryCrate)
        pipe_output = PipeOutput(working_memory=WorkingMemory())

        result = pipe_output.prepare_for_temporal(library_crate=fake_crate)

        assert result is pipe_output
        assert result.working_memory_raw is None
