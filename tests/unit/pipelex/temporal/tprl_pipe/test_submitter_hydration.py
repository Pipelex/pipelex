import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept import Concept
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_class_registry, get_library_manager
from pipelex.pipe_run.exceptions import PipeJobError
from pipelex.temporal.tprl_pipe.submitter_hydration import rehydrate_pipe_output_with_crate


def _text_concept() -> Concept:
    return Concept(
        code="Text",
        domain_code=SpecialDomain.NATIVE,
        description="Plain text",
        structure_class_name="TextContent",
    )


def _pipe_output_with_text(name: str, text: str) -> PipeOutput:
    working_memory = WorkingMemory()
    working_memory.root[name] = Stuff(
        stuff_code="test",
        stuff_name=name,
        concept=_text_concept(),
        content=TextContent(text=text),
    )
    raw = working_memory.dump_for_temporal()
    return PipeOutput(working_memory=WorkingMemory(), working_memory_raw=raw)


class TestRehydratePipeOutputWithCrate:
    @pytest.fixture(autouse=True)
    def _register_text_content(self) -> None:
        registry = get_class_registry()
        if not registry.has_class(name="TextContent"):
            registry.register_class(TextContent)

    def test_returns_same_instance_when_raw_is_none(self, mocker: MockerFixture) -> None:
        pipe_output = PipeOutput(working_memory=WorkingMemory(), working_memory_raw=None)
        open_spy = mocker.spy(get_library_manager(), "open_library")

        result = rehydrate_pipe_output_with_crate(pipe_output, library_crate=None)

        assert result is pipe_output
        assert result.working_memory_raw is None
        assert open_spy.call_count == 0

    def test_no_crate_uses_active_registry(self) -> None:
        """With library_crate=None and only built-in concept, hydration uses the active registry."""
        pipe_output = _pipe_output_with_text("greeting", "Hello, world!")

        result = rehydrate_pipe_output_with_crate(pipe_output, library_crate=None)

        assert result is pipe_output
        assert pipe_output.working_memory_raw is None
        stuff = pipe_output.working_memory.root["greeting"]
        assert isinstance(stuff.content, TextContent)
        assert stuff.content.text == "Hello, world!"

    def test_no_crate_propagates_pipejob_error_for_unknown_class(self) -> None:
        """Without a crate, an unknown structure_class_name raises (existing failure mode)."""
        raw = {
            "root": {
                "bad_stuff": {
                    "stuff_code": "test",
                    "stuff_name": "bad_stuff",
                    "concept": {
                        "code": "NonExistent",
                        "domain_code": "native",
                        "description": "missing",
                        "structure_class_name": "AbsolutelyNonExistentClass",
                    },
                    "content": {"text": "x"},
                },
            },
            "aliases": {},
        }
        pipe_output = PipeOutput(working_memory=WorkingMemory(), working_memory_raw=raw)

        with pytest.raises(PipeJobError):
            rehydrate_pipe_output_with_crate(pipe_output, library_crate=None)

    def test_teardown_runs_on_hydrate_failure_with_crate(self, mocker: MockerFixture) -> None:
        """If hydration raises while a crate scope is open, the scoped library is still torn down."""
        # Mock load_from_crate to be a no-op so we don't need a real crate.
        # The raw dict will trigger a hydrate failure via unknown class.
        from pipelex.libraries.library_crate import LibraryCrate  # noqa: PLC0415

        fake_crate = mocker.MagicMock(spec=LibraryCrate)
        library_manager = get_library_manager()
        teardown_spy = mocker.spy(library_manager, "teardown")
        mocker.patch.object(library_manager, "load_from_crate", return_value=None)

        raw = {
            "root": {
                "bad_stuff": {
                    "stuff_code": "test",
                    "stuff_name": "bad_stuff",
                    "concept": {
                        "code": "NonExistent",
                        "domain_code": "native",
                        "description": "missing",
                        "structure_class_name": "AbsolutelyNonExistentClass",
                    },
                    "content": {"text": "x"},
                },
            },
            "aliases": {},
        }
        pipe_output = PipeOutput(working_memory=WorkingMemory(), working_memory_raw=raw)

        with pytest.raises(PipeJobError):
            rehydrate_pipe_output_with_crate(pipe_output, library_crate=fake_crate)

        assert teardown_spy.call_count == 1, "Scoped rehydration library should be torn down on failure"
