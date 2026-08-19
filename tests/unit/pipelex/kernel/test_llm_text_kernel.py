"""The text path's façade must be as wide as the op beneath it, exercised in DRY mode.

`run_llm_text` takes `concept`, `output_class` and a nullable model choice; the interpreter passes
all three, with the model routinely unset. A façade that hardcodes them is not a convenience over the
op — it is a narrower operation wearing the same name, and the narrowing is silent: a caller
producing a concept that *refines* native `Text` gets `native.Text`/`TextContent` stored where an
interpreted run stores the declared concept and its generated class. Nothing raises at the call;
it raises later, as a `StuffContentTypeError`, in whatever reads the memory back expecting the
declared class. So the gate is on what lands in the returned memory, not on the signature.

DRY mode is what keeps this a unit test: `llm_generate.py` branches to the dry leaf before any worker
lookup, so the `LLMSetting` below names a model the deck never has to resolve. The unset-model case
is the one exception and says so at its assertion.
"""

import pytest

from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.kernel.pipelex_kernel import PipelexKernel
from pipelex.system.pipe_run_mode import PipeRunMode

#: Named but never resolved: the dry leaf short-circuits before a worker is looked up.
DRY_LLM_SETTING = LLMSetting(model="kernel-unit-test-model", temperature=0.5)

USER_PROMPT = "Write a one-line summary."

RESULT_NAME = "summary"


class MeetingSummary(TextContent):
    """A `TextContent` subclass standing in for the class a Text-refining concept generates.

    Declared here rather than pulled from `test_extras` because what matters is only that it is a
    class the façade could not have guessed — the point is that the caller's choice survives.
    """


def _make_dry_kernel() -> PipelexKernel:
    return PipelexKernel.make(storage_scope="test/scope", run_mode=PipeRunMode.DRY, user_id="kernel-unit-test")


class TestLlmTextKernel:
    @pytest.mark.asyncio(loop_scope="class")
    async def test_the_callers_concept_and_output_class_reach_the_memory(self) -> None:
        """The whole point of widening: what the caller declared is what gets stored."""
        concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.ANYTHING)

        result = await _make_dry_kernel().llm_text(
            memory=WorkingMemoryFactory.make_empty(),
            model=DRY_LLM_SETTING,
            user=USER_PROMPT,
            concept=concept,
            output_class=MeetingSummary,
            result=RESULT_NAME,
        )

        stuff = result.memory.get_stuff(name=RESULT_NAME)
        assert type(stuff.content) is MeetingSummary, (
            "the caller's `output_class` must reach the op — hardcoding `TextContent` stores a class the "
            "caller never asked for, and only blows up later in whoever reads the memory back."
        )
        assert stuff.concept.concept_ref == concept.concept_ref, (
            "the caller's `concept` must reach the op — an interpreted run stores the declared concept, so "
            "hardcoding native Text is exactly the two-readers-disagree shape this gate exists to catch."
        )

    @pytest.mark.asyncio(loop_scope="class")
    async def test_the_defaults_are_what_the_method_used_to_hardcode(self) -> None:
        """Widening had to stay additive: omitting both must reproduce the previous behavior exactly."""
        result = await _make_dry_kernel().llm_text(
            memory=WorkingMemoryFactory.make_empty(),
            model=DRY_LLM_SETTING,
            user=USER_PROMPT,
            result=RESULT_NAME,
        )

        stuff = result.memory.get_stuff(name=RESULT_NAME)
        assert type(stuff.content) is TextContent
        assert stuff.concept.concept_ref == NativeConceptCode.TEXT.concept_ref
