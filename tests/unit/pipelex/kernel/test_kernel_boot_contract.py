"""A kernel call is servable on a `RuntimeBoot`-only process with zero `.mthds` loaded.

This is the kernel's *contract*, not a consequence of one — the whole point of extracting operator
semantics out of the interpreter is that a programmatic caller can invoke them without a library, a
router or a pipeline manager. So it is pinned permanently here rather than proven once by hand.

Three layers already guard neighbouring properties and none of them covers this one. The static
hub-layering guard proves no kernel *module* imports `interpreter_hub`.
`test_kernel_layer_import_closure.py` proves `pipelex.kernel.pipelex_kernel` *imports* clean.
`test_runtime_boot_closure.py` proves `RuntimeBoot.make()` *boots* clean. What none of them does is
**call** a kernel op on that boot — and a call is where a kernel-only process would actually break:
by resolving out of a registry the interpreter half fills (`OrchestratorRegistry`,
`BundleValidatorRegistry`, the PipeFunc executor modes are all empty here), or by reaching the
interpreter through a function-local import, which is invisible to the static graph and to the
import-closure test *at once*. The sweep below therefore runs **after** the kernel call, which is
what makes this test strictly stronger than the import-time one it complements.

**Every kernel entry point is called, not a representative one** — the seven operator arms and the
memory-boundary ops (`shape_inputs` and the four extraction helpers), with the three
`resolve_*_setting` helpers the sole exception, for the deck reason given below. The blind spot this test
exists for is per-function, so covering one op says nothing about the next: a function-local import
inside `run_search` is caught only by calling `run_search`. That also makes this the only gate the
ops modules other than `llm_ops` have — `PipelexKernel` is an LLM-era façade that does not import
them, so `test_kernel_layer_import_closure.py`'s `pipelex.kernel.pipelex_kernel` entry point does not
reach them even at import time.

The memory-boundary arm carries a second proof the operator arms cannot: `shape_inputs` needs a
`ConceptProviderAbstract`, and the only implementation in the tree is the interpreter's concept
library. The script therefore supplies its own, which is what a library-free caller has to do — so
the arm demonstrates the shape of that caller as well as pinning the closure.

Run in a **subprocess** for the reason its two siblings state: a suite-level boot already owns the
process singletons, and both hubs are sticky class attributes that `teardown` deliberately does not
clear — so an in-process check would answer from a stale `Pipelex` and pass vacuously.

`needs_inference=False` keeps the boot offline (no gateway terms gate, no model-deck validation), and
`PipeRunMode.DRY` keeps the call offline: every cogt leaf mocks before a worker is looked up, so each
setting below names a model the deck never has to resolve. The settings are built literally rather
than through the `resolve_*_setting` helpers for that same reason — those read the deck, which is a
separate question from the one this test asks.

**On the once-deferred orchestrator question.** `runtime_boot.py`'s orchestrator-rejection comment used
to defer the external-interpreter-orchestrator half-application hole to "the first caller of a
kernel-only boot", which is this test. That hole is now closed, and not by this test: the plugin
entry-point group split scopes a kernel-only boot's discovery to `KERNEL_ENTRY_POINT_GROUPS`, so an
interpreter-group orchestrator is never registered and the existing gate rejects its name loudly.
Neither remedy the earlier analysis proposed was built.
"""

import subprocess  # noqa: S404
import sys
import textwrap

from tests.unit.pipelex.test_kernel_layer_import_closure import INTERPRETER_PACKAGES

#: Wall-clock bound on the kernel-call subprocess, matching both sibling harnesses: a boot or a call
#: that deadlocks must present as a failure, not as a hung suite
#: (`docs/agents/debugging-hanging-pytest-runs.md`).
SUBPROCESS_TIMEOUT_SECONDS = 300

#: Boot the kernel layer in a fresh interpreter, run **every** operator's kernel entry point, assert
#: the typed results, and only then sweep `sys.modules`. The order is the point: a function-local
#: interpreter import inside a kernel op would land in `sys.modules` during the call and nowhere else.
#: Both LLM arms run because they share almost nothing below the façade — `resolve_llm_setting_for_text`
#: vs `_for_object`, and `dry_llm_gen_text` vs `dry_llm_gen_object` — so covering one leaves the
#: other's closure unproven, and the contract is stated over *a kernel call*, not over one of them.
#: The five operator ops below are called as module-level functions rather than through `PipelexKernel`
#: for the plain reason that the façade does not expose them.
_KERNEL_CALL_SCRIPT = textwrap.dedent(
    """
    import asyncio
    import sys

    from typing_extensions import override

    from pipelex.cogt.extract.extract_input import ExtractInput
    from pipelex.cogt.extract.extract_setting import ExtractSetting
    from pipelex.cogt.img_gen.img_gen_setting import ImgGenSetting
    from pipelex.cogt.llm.llm_setting import LLMSetting
    from pipelex.cogt.search.search_setting import SearchSetting
    from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
    from pipelex.core.concepts.concept import Concept
    from pipelex.core.concepts.concept_factory import ConceptFactory
    from pipelex.core.concepts.concept_provider_abstract import ConceptProviderAbstract
    from pipelex.core.concepts.native.concept_native import NativeConceptCode
    from pipelex.core.memory.working_memory import WorkingMemory
    from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
    from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
    from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
    from pipelex.core.stuffs.image_content import ImageContent
    from pipelex.core.stuffs.list_content import ListContent
    from pipelex.core.stuffs.number_content import NumberContent
    from pipelex.core.stuffs.search_result_content import SearchResultContent
    from pipelex.core.stuffs.stuff_content import StuffContent
    from pipelex.core.stuffs.stuff_factory import StuffFactory
    from pipelex.core.stuffs.text_content import TextContent
    from pipelex.kernel.compose_ops import run_compose_template
    from pipelex.kernel.extract_ops import build_extract_job_params, run_extract
    from pipelex.kernel.func_ops import run_func
    from pipelex.kernel.img_gen_ops import build_img_gen_job_params, run_img_gen
    from pipelex.kernel.img_gen_prompt import assemble_img_gen_prompt
    from pipelex.kernel.llm_results import LlmObjectResult, LlmTextResult
    from pipelex.kernel.memory_ops import (
        extract_main_content,
        extract_main_content_as_list,
        extract_named_content,
        extract_named_content_as_list,
        shape_inputs,
    )
    from pipelex.kernel.pipelex_kernel import PipelexKernel
    from pipelex.kernel.prompt_references import ImageReference, ImageReferenceKind
    from pipelex.kernel.search_ops import run_search
    from pipelex.runtime_boot import RuntimeBoot
    from pipelex.system.pipe_run_mode import PipeRunMode
    from pipelex.system.registries.class_registry_access import get_class_registry
    from pipelex.system.registries.func_registry import func_registry
    from pipelex.system.runtime import IntegrationMode
    from pipelex.tools.jinja2.template_category import TemplateCategory

    interpreter_packages = frozenset(sys.argv[1:])
    # An empty set would make the sweep flag nothing and the test pass vacuously — the same guard both
    # sibling harnesses carry, for the same reason.
    if not interpreter_packages:
        print("no interpreter packages passed — the sweep would match nothing")
        raise SystemExit(2)

    def fail(message):
        print(message)
        raise SystemExit(1)

    def check_stored(result, label, expected_type):
        # Every op ends by writing what it produced into memory as the new main stuff, and that
        # write-back is the half a kernel-only caller most depends on — so each arm checks it landed.
        # Checked by type rather than by identity because the two are not universally the same object:
        # `ExtractResult` narrows its `content` field below `StuffContent`, so pydantic revalidates it
        # into a fresh container (see `pipelex/kernel/extract_results.py`).
        stored = result.memory.get_main_stuff().content
        if not isinstance(stored, expected_type):
            fail(f"the memory returned by {label} carries {type(stored).__name__}, not the {expected_type.__name__} it produced")

    class NativeOnlyConceptProvider(ConceptProviderAbstract):
        # A caller without a loaded library still has to answer concept questions, and this is what
        # that costs on a kernel-only boot: native concepts from the pure factory, compatibility
        # from the declaration tier the kernel doctrine routes to, and structure classes from the
        # class registry a RuntimeBoot fills. `shape_inputs` takes the provider explicitly for
        # exactly this reason — the interpreter hands over its library, a programmatic caller hands
        # over something like this.
        @override
        def get_required_concept(self, concept_ref):
            return ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode(concept_ref.split(".")[-1]))

        @override
        def get_native_concept(self, native_concept):
            return ConceptFactory.make_native_concept(native_concept_code=native_concept)

        @override
        def get_required_entry_concept(self, concept_ref_or_code, *, search_scope=None):
            return self.get_required_concept(concept_ref_or_code)

        @override
        def is_compatible(self, *, tested_concept, wanted_concept, strict=False):
            return Concept.are_compatible_by_declaration(concept_1=tested_concept, concept_2=wanted_concept)

        @override
        def get_structure_class(self, *, concept):
            return get_class_registry().get_required_subclass(name=concept.structure_class_name, base_class=StuffContent)

    RuntimeBoot.make(integration_mode=IntegrationMode.PYTEST, needs_inference=False)

    kernel = PipelexKernel.make(run_mode=PipeRunMode.DRY, user_id="kernel-boot-contract")
    model = LLMSetting(model="kernel-boot-contract-model", temperature=0.5)
    text_concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT)

    # The input end of the memory boundary, driven the way a library-free caller drives it: raw values
    # plus the specs it declares for them. The shaped memory is then what the first op runs on, so the
    # two ends of the boundary are proven against each other rather than in isolation.
    SHAPED_TOPIC = "what a kernel-only boot can run"
    shaped_memory = shape_inputs(
        inputs={"topic": SHAPED_TOPIC},
        concept_provider=NativeOnlyConceptProvider(),
        input_specs=InputStuffSpecs(root={"topic": StuffSpec(concept=text_concept)}),
    )
    if extract_named_content(memory=shaped_memory, name="topic", content_type=TextContent).text != SHAPED_TOPIC:
        fail("shape_inputs did not land the provided value under its declared name")

    object_result = asyncio.run(
        kernel.llm_object(
            memory=shaped_memory,
            output_class=NumberContent,
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.NUMBER),
            model=model,
            user="Pick a number.",
            result="answer",
        )
    )

    if not isinstance(object_result, LlmObjectResult):
        fail(f"llm_object returned {type(object_result).__name__}, not an LlmObjectResult")
    if not isinstance(object_result.content, NumberContent):
        fail(f"llm_object produced {type(object_result.content).__name__}, not the NumberContent it was given")
    if object_result.memory.get_main_stuff().content is not object_result.content:
        fail("the memory returned by llm_object does not carry the produced content as its main stuff")

    # The read end of the boundary, on the memory the call returned: the produced content narrowed to
    # the class it was asked for (the result envelope annotates that field as the base StuffContent),
    # and the shaped input still readable beside it.
    if extract_main_content(memory=object_result.memory, content_type=NumberContent) is not object_result.content:
        fail("extract_main_content did not return the content llm_object produced")
    if extract_named_content(memory=object_result.memory, name="topic", content_type=TextContent).text != SHAPED_TOPIC:
        fail("the shaped input did not survive the kernel call it was passed into")

    # The multi-output shape, which the single-content reads above cannot narrow: it is stored as one
    # ListContent, so it needs the list reads to come back typed down to the item.
    list_result = asyncio.run(
        kernel.llm_object(
            memory=WorkingMemoryFactory.make_empty(),
            output_class=NumberContent,
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.NUMBER),
            model=model,
            user="Pick a few numbers.",
            result="answers",
            is_multiple_output=True,
        )
    )

    if not isinstance(list_result.content, ListContent):
        fail(f"llm_object(is_multiple_output=True) produced {type(list_result.content).__name__}, not a ListContent")
    for extracted_list in (
        extract_main_content_as_list(memory=list_result.memory, item_type=NumberContent),
        extract_named_content_as_list(memory=list_result.memory, name="answers", item_type=NumberContent),
    ):
        if not extracted_list.items:
            fail("a list extraction helper returned no items for a multiple-output result")
        for extracted_item in extracted_list.items:
            if not isinstance(extracted_item, NumberContent):
                fail(f"a list extraction helper yielded a {type(extracted_item).__name__}, not the NumberContent it was asked for")

    text_result = asyncio.run(
        kernel.llm_text(
            memory=WorkingMemoryFactory.make_empty(),
            model=model,
            user="Say something.",
            result="reply",
        )
    )

    if not isinstance(text_result, LlmTextResult):
        fail(f"llm_text returned {type(text_result).__name__}, not an LlmTextResult")
    main_text_content = text_result.memory.get_main_stuff().content
    if not isinstance(main_text_content, TextContent):
        fail(f"llm_text landed {type(main_text_content).__name__} in memory, not a TextContent")
    if main_text_content.text != text_result.text:
        fail("the memory returned by llm_text does not carry the text the result reports")

    extract_setting = ExtractSetting(model="kernel-boot-contract-extract-model")
    extract_result = asyncio.run(
        run_extract(
            memory=WorkingMemoryFactory.make_empty(),
            extract_input=ExtractInput(document_uri="https://example.com/kernel-boot-contract.pdf"),
            extract_setting=extract_setting,
            extract_job_params=build_extract_job_params(extract_setting=extract_setting),
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.PAGE),
            job_metadata=kernel.make_step_metadata(),
            cogt_run_params=kernel.cogt_run_params,
            result_name="pages",
        )
    )

    # An extraction always lands a page sequence, even from a single image — there is no multiplicity
    # fork on this path, so the ListContent is the shape and not one of two.
    if not isinstance(extract_result.content, ListContent):
        fail(f"run_extract produced {type(extract_result.content).__name__}, not the ListContent of pages it owes")
    check_stored(extract_result, "run_extract", ListContent)

    # The image arm runs the pair, assemble then generate, rather than handing `run_img_gen` a prompt
    # built in the test. It could not do otherwise before `assemble_img_gen_prompt` existed, because
    # the only builder was an interpreter-layer blueprint — so this arm's coverage was incomplete in
    # exactly the way the kernel surface was. Assembly is also the half that reaches into memory to
    # resolve references, which is where a function-local interpreter import would hide, and this
    # subprocess is the only gate that can see one.
    img_gen_memory = WorkingMemoryFactory.make_from_single_stuff(
        StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
            content=ImageContent(url="https://example.com/kernel-boot-contract-reference.png"),
            name="reference",
        )
    )
    img_gen_prompt = asyncio.run(
        assemble_img_gen_prompt(
            context_provider=img_gen_memory,
            prompt_blueprint=TemplateBlueprint(
                template="Draw something like {{ reference }}.",
                category=TemplateCategory.IMG_GEN_PROMPT,
            ),
            image_references=[ImageReference(variable_path="reference", kind=ImageReferenceKind.DIRECT)],
        )
    )
    # The token and the input image are two readings of one registry; asserting only that the call
    # returned would leave the half that actually reaches into memory — reference resolution —
    # unproven on a boot that has no library.
    if "[Image 1]" not in img_gen_prompt.positive_text:
        fail(f"assemble_img_gen_prompt left the referenced image unsubstituted: {img_gen_prompt.positive_text!r}")
    if not img_gen_prompt.input_images or len(img_gen_prompt.input_images) != 1:
        fail("assemble_img_gen_prompt did not carry the referenced image through to input_images")

    img_gen_setting = ImgGenSetting(model="kernel-boot-contract-img-gen-model")
    img_gen_result = asyncio.run(
        run_img_gen(
            memory=img_gen_memory,
            img_gen_prompt=img_gen_prompt,
            img_gen_setting=img_gen_setting,
            img_gen_job_params=build_img_gen_job_params(img_gen_setting=img_gen_setting),
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
            output_class=ImageContent,
            job_metadata=kernel.make_step_metadata(),
            cogt_run_params=kernel.cogt_run_params,
            result_name="picture",
        )
    )

    if not isinstance(img_gen_result.content, ImageContent):
        fail(f"run_img_gen produced {type(img_gen_result.content).__name__}, not the ImageContent class it was given")
    check_stored(img_gen_result, "run_img_gen", ImageContent)

    search_query = "What runs on a kernel-only boot?"
    search_result = asyncio.run(
        run_search(
            memory=WorkingMemoryFactory.make_empty(),
            template=search_query,
            category=TemplateCategory.LLM_PROMPT,
            search_setting=SearchSetting(model="kernel-boot-contract-search-model"),
            concept=text_concept,
            job_metadata=kernel.make_step_metadata(),
            cogt_run_params=kernel.cogt_run_params,
            result_name="findings",
        )
    )

    # The rendered query is what proves the templating ran here rather than being skipped: it is the
    # one part of a search step that is not the provider's.
    if search_result.rendered_query != search_query:
        fail(f"run_search rendered {search_result.rendered_query!r}, not the query it was given")
    check_stored(search_result, "run_search", SearchResultContent)

    composed_text = "Composed on a kernel-only boot."
    compose_result = asyncio.run(
        run_compose_template(
            memory=WorkingMemoryFactory.make_empty(),
            template=composed_text,
            category=TemplateCategory.LLM_PROMPT,
            concept=text_concept,
            output_class=TextContent,
            result_name="composed",
        )
    )

    if compose_result.rendered_text != composed_text:
        fail(f"run_compose_template rendered {compose_result.rendered_text!r}, not the template it was given")
    check_stored(compose_result, "run_compose_template", TextContent)

    # Registered here rather than imported, because the func path's whole point is that the function is
    # the caller's: a kernel-only process has no library to have registered one for it.
    FUNCTION_NAME = "kernel_boot_contract_function"
    FUNCTION_TEXT = "produced by a registered function"

    def produce_text(working_memory: WorkingMemory) -> TextContent:
        return TextContent(text=FUNCTION_TEXT)

    func_registry.register_function(produce_text, name=FUNCTION_NAME)

    func_result = asyncio.run(
        run_func(
            memory=WorkingMemoryFactory.make_empty(),
            function_name=FUNCTION_NAME,
            concept=text_concept,
            result_name="called",
        )
    )

    if not isinstance(func_result.content, TextContent) or func_result.content.text != FUNCTION_TEXT:
        fail("run_func did not return what the registered function produced")
    check_stored(func_result, "run_func", TextContent)

    # Swept last, so a function-local interpreter import taken during any of the calls is caught too.
    offenders = sorted(
        name
        for name in sys.modules
        if name.startswith("pipelex.") and name.split(".")[1] in interpreter_packages
    )
    if offenders:
        print(f"the kernel call loaded {len(offenders)} interpreter module(s): {offenders}")
        raise SystemExit(1)
    if "pipelex.interpreter_hub" in sys.modules:
        print("the kernel call loaded pipelex.interpreter_hub")
        raise SystemExit(1)

    print("kernel boot contract OK")
    """
)

#: The negative control. The sweep lives inside a `textwrap.dedent` string, so nothing type-checks or
#: lints the logic in it — a broken predicate would leave the real case green forever while flagging
#: nothing, and the real case cannot detect its own blindness. `cogt` is the control package because
#: an LLM kernel call loads it by definition, so calling it an "interpreter package" must come back a
#: failure, reported as offending modules. Both sibling harnesses carry the same control.
CONTROL_PACKAGE_THE_KERNEL_ALWAYS_LOADS = "cogt"


def _run_kernel_call(*, interpreter_packages: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    """Boot the kernel layer in a fresh interpreter, call the kernel, and return the verdict."""
    try:
        return subprocess.run(  # noqa: S603
            [sys.executable, "-c", _KERNEL_CALL_SCRIPT, *interpreter_packages],
            capture_output=True,
            text=True,
            check=False,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        message = f"the kernel boot-contract subprocess did not finish within {SUBPROCESS_TIMEOUT_SECONDS}s"
        raise AssertionError(message) from exc


class TestKernelBootContract:
    def test_the_sweep_still_detects_a_package_the_kernel_call_really_loads(self) -> None:
        """The control: same script, opposite verdict. Without this, the real case below is vacuous."""
        result = _run_kernel_call(interpreter_packages=(CONTROL_PACKAGE_THE_KERNEL_ALWAYS_LOADS,))

        assert result.returncode == 1, (
            f"treating {CONTROL_PACKAGE_THE_KERNEL_ALWAYS_LOADS!r} as an interpreter package must fail — "
            "an LLM kernel call loads it by definition. This passing means the sweep has stopped sweeping, "
            "and the real case below now proves nothing.\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        assert "interpreter module(s)" in result.stdout
        assert "kernel boot contract OK" not in result.stdout

    def test_every_kernel_call_runs_on_a_kernel_only_boot_with_no_library(self) -> None:
        result = _run_kernel_call(interpreter_packages=INTERPRETER_PACKAGES)

        assert result.returncode == 0, (
            "every kernel call must be servable on a RuntimeBoot-only process with zero .mthds loaded, and must "
            "load no interpreter module doing it. This is the kernel's contract — see pipelex/kernel/__init__.py "
            "for the doctrine and docs/contribute/hub-layering.md for how to find the shortest import path to an "
            "offender.\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        assert "kernel boot contract OK" in result.stdout
