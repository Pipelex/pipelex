import pytest

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.registries.func_registry import pipe_func

_BUNDLE = """
domain = "batch_item_isolation"
description = "A batch whose branch function rewrites the item it is given"
main_pipe = "shout_every_note"

[pipe.shout_every_note]
type = "PipeBatch"
description = "Shouts every note"
inputs = { notes = "Text[]" }
output = "Text[]"
branch_pipe_code = "shout_note"
input_list_name = "notes"
input_item_name = "note"

[pipe.shout_note]
type = "PipeFunc"
description = "Shouts one note, rewriting the item it was handed in place"
inputs = { note = "Text" }
output = "Text"
function_name = "tests.integration.pipelex.pipes.controller.pipe_batch.test_pipe_batch_item_isolation.batch_item_isolation_shout_note"
"""


@pipe_func()
def batch_item_isolation_shout_note(working_memory: WorkingMemory) -> TextContent:
    note = working_memory.get_stuff_as_text(name="note")
    note.text = note.text.upper()
    return TextContent(text=f"{note.text}!")


@pytest.mark.asyncio(loop_scope="class")
class TestPipeBatchItemIsolation:
    async def test_a_branch_rewriting_its_item_leaves_the_batched_list_unchanged(self) -> None:
        """Each branch gets its own copy of its item, as it gets its own copy of the rest of working memory."""
        result = await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.LIVE).execute(
            mthds_contents=[_BUNDLE],
            inputs={"notes": {"concept": "native.Text", "content": [{"text": "bread"}, {"text": "milk"}]}},
        )

        working_memory = result.pipe_output.working_memory
        shouted = working_memory.main_stuff_as_list(item_type=TextContent)
        assert [item.text for item in shouted.items] == ["BREAD!", "MILK!"]
        notes = working_memory.get_stuff_as_list("notes", item_type=TextContent)
        assert [item.text for item in notes.items] == ["bread", "milk"]
