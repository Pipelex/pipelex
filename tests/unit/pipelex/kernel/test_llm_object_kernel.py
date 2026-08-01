"""The object path's two kernel-only arms, exercised through the façade in DRY mode.

Neither arm is reachable from the re-pointed interpreter suite, which is why they live here rather
than being left to the zero-behavior-change backstop:

- **Structure-prompt provenance.** `PipeLLM` never supplies a `structure_prompt` and always rides the
  kernel's derivation; `PipeStructure` always supplies one and never derives. No interpreter test
  therefore observes the *choice* between the two on one code path. The sentinel is `is not None`
  rather than falsiness, so an empty string is a real "no structure prompt at all" override — a
  rewrite to `structure_prompt or await derive_structure_prompt(...)` would silently turn that arm
  back into a derivation, and only the empty-string case below would notice.
- **The memory contract.** A kernel call may mutate the memory it is passed and *returns* it; callers
  must treat the returned memory as the result. Inline execution aliases the two, so an interpreter
  test that reads the argument back cannot tell the two apart — which is exactly the aliasing the
  contract tells callers not to depend on.

DRY mode is what keeps these unit tests: `llm_generate.py` branches to the dry leaf *before* any
worker lookup, so the `LLMSetting` below names a model the deck never has to resolve.
"""

import pytest

from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.kernel.llm_results import StructuringPath
from pipelex.kernel.method_kernel import MethodKernel
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.test_extras.registry_test_models import FictionCharacter

#: Named but never resolved: the dry leaf short-circuits before a worker is looked up, so this stays
#: a unit test instead of acquiring a dependency on whatever the deck happens to contain.
DRY_LLM_SETTING = LLMSetting(model="kernel-unit-test-model", temperature=0.5)

USER_PROMPT = "Invent a character."

SUPPLIED_STRUCTURE_PROMPT = "\n\nAnswer as a character sheet."

#: A field name of `FictionCharacter` that appears in the *derived* structure prompt and nowhere else
#: in this module — the marker that says which of the two provenances produced the prompt.
FIELD_ONLY_THE_DERIVATION_NAMES = "backstory"

RESULT_NAME = "character"


def _make_dry_kernel() -> MethodKernel:
    return MethodKernel.make(run_mode=PipeRunMode.DRY, user_id="kernel-unit-test")


class TestLlmObjectKernel:
    @pytest.mark.asyncio(loop_scope="class")
    async def test_the_structure_prompt_is_derived_from_the_output_class_by_default(self) -> None:
        result = await _make_dry_kernel().llm_object(
            memory=WorkingMemoryFactory.make_empty(),
            output_class=FictionCharacter,
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.ANYTHING),
            model=DRY_LLM_SETTING,
            user=USER_PROMPT,
            result=RESULT_NAME,
        )

        user_text = result.rendered_prompt.user_text
        assert user_text is not None
        assert user_text.startswith(USER_PROMPT)
        assert FIELD_ONLY_THE_DERIVATION_NAMES in user_text, (
            "with no structure prompt supplied, the kernel must derive one from `output_class` — this is "
            "what keeps both callers producing the same prompt by default instead of forking their defaults."
        )

    @pytest.mark.asyncio(loop_scope="class")
    @pytest.mark.parametrize(
        "structure_prompt",
        [
            pytest.param(SUPPLIED_STRUCTURE_PROMPT, id="supplied_text_replaces_the_derivation"),
            pytest.param("", id="empty_string_overrides_with_no_structure_prompt_at_all"),
        ],
    )
    async def test_a_supplied_structure_prompt_replaces_the_derivation(self, structure_prompt: str) -> None:
        result = await _make_dry_kernel().llm_object(
            memory=WorkingMemoryFactory.make_empty(),
            output_class=FictionCharacter,
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.ANYTHING),
            model=DRY_LLM_SETTING,
            user=USER_PROMPT,
            structure_prompt=structure_prompt,
            result=RESULT_NAME,
        )

        assert result.rendered_prompt.user_text == USER_PROMPT + structure_prompt
        assert FIELD_ONLY_THE_DERIVATION_NAMES not in (result.rendered_prompt.user_text or "")

    @pytest.mark.asyncio(loop_scope="class")
    async def test_the_produced_content_lands_in_the_returned_memory(self) -> None:
        """The returned memory is the result — asserted here, and asserted *only* here.

        That the argument happens to be the same object today is deliberately not asserted: it is the
        aliasing the contract forbids callers from relying on, and pinning it in a test would make the
        very change the contract exists to permit (a serialization boundary between the two) look like
        a regression.
        """
        result = await _make_dry_kernel().llm_object(
            memory=WorkingMemoryFactory.make_empty(),
            output_class=FictionCharacter,
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.ANYTHING),
            model=DRY_LLM_SETTING,
            user=USER_PROMPT,
            result=RESULT_NAME,
        )

        assert isinstance(result.content, FictionCharacter)
        assert result.structuring_path == StructuringPath.OBJECT_DIRECT
        assert result.memory.get_stuff(name=RESULT_NAME).content is result.content
        assert result.memory.get_main_stuff().content is result.content
