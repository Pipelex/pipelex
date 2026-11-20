"""What a PipeBatch branch starts with: its own copy of what its pipe reads and of its item, never a copy of the whole
working memory. A branch that copied the whole memory, the batched list included, made a batch's start cost its width
times its list's size, which held a durable backend's workflow thread past its deadline.
"""

from collections.abc import Callable

import pytest
from typing_extensions import override

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_pipe_library, scoped_pipe_router
from pipelex.pipe_controllers.batch.pipe_batch import PipeBatch
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_router import PipeRouter
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.registries.func_registry import pipe_func

_DOMAIN_CODE = "test_batch_branch_memory"
_NOTES = ["bread", "milk", "eggs"]


@pipe_func()
def batch_branch_memory_tag_note(working_memory: WorkingMemory) -> TextContent:
    """Tag the note with the context as this branch received it, then rewrite both in place, as a function may."""
    note = working_memory.get_stuff_as_text(name="note")
    context = working_memory.get_stuff_as_text(name="context")
    tagged = f"{note.require_text()}|{context.require_text()}"
    note.text = note.require_text().upper()
    context.text = "rewritten by a branch"
    return TextContent(text=tagged)


class _BranchMemoryRecordingRouter(PipeRouter):
    """Real in-process router that records the names each batch branch's working memory holds when it starts."""

    def __init__(self) -> None:
        super().__init__()
        self.branch_memory_keys: list[set[str]] = []

    @override
    async def run_batch_branch(self, pipe_job: PipeJob) -> PipeOutput:
        self.branch_memory_keys.append(set(pipe_job.get_working_memory().list_keys()))
        return await super().run_batch_branch(pipe_job)


def _build_batch() -> PipeBatch:
    """A batch over notes whose branch reads its note and a shared context, and rewrites both."""
    tag_pipe = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="branch_memory_tag",
        blueprint=PipeFuncBlueprint(
            description="Tag the note with the context",
            inputs={"note": "Text", "context": "Text"},
            output="Text",
            function_name=f"{__name__}.batch_branch_memory_tag_note",
        ),
    )
    pipe_library = get_pipe_library()
    pipe_library.add_new_pipe(pipe=tag_pipe)

    batch = PipeFactory[PipeBatch].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="branch_memory_batch",
        blueprint=PipeBatchBlueprint(
            description="Tag every note",
            # Domain-qualified: this blueprint is hand-built, so it never goes through the crate qualification pass.
            branch_pipe_code=f"{_DOMAIN_CODE}.branch_memory_tag",
            output="Text",
            input_list_name="notes",
            input_item_name="note",
            inputs={"notes": "Text", "context": "Text"},
        ),
    )
    pipe_library.add_new_pipe(pipe=batch)
    return batch


def _make_memory(batch: PipeBatch) -> WorkingMemory:
    """The batched notes, the context the branch reads, and a stuff the branch pipe does not read."""
    text_concept = batch.inputs.get_required_stuff_spec("notes").concept
    working_memory = WorkingMemoryFactory.make_from_single_stuff(
        StuffFactory.make_stuff(
            concept=text_concept,
            content=ListContent[TextContent](items=[TextContent(text=note) for note in _NOTES]),
            name="notes",
        )
    )
    working_memory.add_new_stuff(
        name="context", stuff=StuffFactory.make_stuff(concept=text_concept, content=TextContent(text="kitchen"), name="context")
    )
    working_memory.add_new_stuff(
        name="unrelated", stuff=StuffFactory.make_stuff(concept=text_concept, content=TextContent(text="not read by the branch"), name="unrelated")
    )
    return working_memory


@pytest.mark.asyncio(loop_scope="class")
class TestPipeBatchBranchMemory:
    async def test_a_branch_starts_with_what_its_pipe_reads_and_isolated(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """Each branch holds its item and the inputs its pipe reads, not the batched list nor what its pipe never reads.

        A regression to a copy of the whole working memory per branch puts `notes` and `unrelated` back in every branch.
        What each branch holds is its own: every branch read the context as the batch held it, though each rewrote it.
        """
        load_empty_library()
        batch = _build_batch()
        working_memory = _make_memory(batch)
        router = _BranchMemoryRecordingRouter()

        with scoped_pipe_router(router):
            pipe_output = await batch.run_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE),
            )

        assert router.branch_memory_keys == [{"note", "context", "main_stuff"}] * len(_NOTES)
        tagged = pipe_output.working_memory.main_stuff_as_list(item_type=TextContent)
        assert [item.require_text() for item in tagged.items] == [f"{note}|kitchen" for note in _NOTES]
        assert working_memory.get_stuff_as_str("context") == "kitchen"
        notes = working_memory.get_stuff_as_list("notes", item_type=TextContent)
        assert [item.require_text() for item in notes.items] == _NOTES
