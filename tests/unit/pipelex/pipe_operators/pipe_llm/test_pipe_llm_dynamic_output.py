"""Unit tests for `PipeLLM._resolve_dynamic_output_concept_if_needed`.

When a PipeLLM declares `output = "Dynamic"`, the actual output concept is supplied
at run time via `pipe_run_params.dynamic_output_concept_ref` (or the legacy
`params[DYNAMIC_OUTPUT_CONCEPT]` key). The resolver mutates `self.output.concept`
so downstream synthesis/validation operates on the resolved concept rather than
`native.Dynamic` (which is an empty `StuffContent` subclass and would silently
drop every field returned by the LLM).

These tests pin the behavior of the resolver in isolation:

- explicit override (qualified ref or bare code) → concept becomes the resolved one
- no override → concept defaults to `native.Text`
- non-Dynamic output → resolver is a no-op
"""

from typing import Callable

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_run.pipe_run_params import PipeRunParamKey
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory


def _make_pipe(domain_code: str, pipe_code: str, output: str) -> PipeLLM:
    blueprint = PipeLLMBlueprint(
        description="dynamic-output test pipe",
        inputs={"user_text": "native.Text"},
        output=output,
        prompt="Process @user_text",
    )
    return PipeFactory[PipeLLM].make_from_blueprint(
        domain_code=domain_code,
        pipe_code=pipe_code,
        blueprint=blueprint,
    )


class TestPipeLLMDynamicOutputResolution:
    def test_fallback_to_native_text_when_no_override(
        self,
        load_empty_library: Callable[[], str],
    ):
        """Regression: when the run params provide no override, the resolver must still
        replace the `Dynamic` concept (previously, the fallback was assigned to a local
        variable but never applied to `self.output.concept`, so downstream code ran with
        `Dynamic` and the LLM's structured JSON deserialized to `{}`).
        """
        load_empty_library()
        pipe_llm = _make_pipe(domain_code="test_domain", pipe_code="test_dyn_fallback", output="native.Dynamic")
        params = PipeRunParamsFactory.make_run_params()  # no dynamic_output_concept_ref

        pipe_llm.resolve_dynamic_output_concept_if_needed(pipe_run_params=params)

        assert pipe_llm.output.concept.code == NativeConceptCode.TEXT
        assert pipe_llm.output.concept.domain_code == SpecialDomain.NATIVE

    def test_override_with_qualified_native_ref(
        self,
        load_empty_library: Callable[[], str],
    ):
        load_empty_library()
        pipe_llm = _make_pipe(domain_code="test_domain", pipe_code="test_dyn_qualified", output="native.Dynamic")
        params = PipeRunParamsFactory.make_run_params(dynamic_output_concept_ref="native.Number")

        pipe_llm.resolve_dynamic_output_concept_if_needed(pipe_run_params=params)

        assert pipe_llm.output.concept.code == NativeConceptCode.NUMBER
        assert pipe_llm.output.concept.domain_code == SpecialDomain.NATIVE

    def test_override_with_bare_code_uses_pipe_domain(
        self,
        load_empty_library: Callable[[], str],
    ):
        """A bare concept code (no `domain.` prefix) is resolved against the pipe's own
        domain — for native concepts that means `native.<Code>` is found in the library.
        This guards against accidental double-prefixing (`test_domain.native.Number`).
        """
        load_empty_library()
        pipe_llm = _make_pipe(domain_code="test_domain", pipe_code="test_dyn_bare", output="native.Dynamic")
        params = PipeRunParamsFactory.make_run_params(dynamic_output_concept_ref="Number")

        pipe_llm.resolve_dynamic_output_concept_if_needed(pipe_run_params=params)

        assert pipe_llm.output.concept.code == NativeConceptCode.NUMBER
        assert pipe_llm.output.concept.domain_code == SpecialDomain.NATIVE

    def test_legacy_params_key_override(
        self,
        load_empty_library: Callable[[], str],
    ):
        """Legacy callers set the override via `params[_dynamic_output_concept]` instead
        of the dedicated field. The resolver must honor it as a fallback so existing
        integrations keep working.
        """
        load_empty_library()
        pipe_llm = _make_pipe(domain_code="test_domain", pipe_code="test_dyn_legacy", output="native.Dynamic")
        params = PipeRunParamsFactory.make_run_params(params={PipeRunParamKey.DYNAMIC_OUTPUT_CONCEPT: "native.Number"})

        pipe_llm.resolve_dynamic_output_concept_if_needed(pipe_run_params=params)

        assert pipe_llm.output.concept.code == NativeConceptCode.NUMBER
        assert pipe_llm.output.concept.domain_code == SpecialDomain.NATIVE

    def test_non_dynamic_output_is_unchanged(
        self,
        load_empty_library: Callable[[], str],
    ):
        load_empty_library()
        pipe_llm = _make_pipe(domain_code="test_domain", pipe_code="test_dyn_non_dynamic", output="native.Text")
        params = PipeRunParamsFactory.make_run_params(dynamic_output_concept_ref="native.Number")

        pipe_llm.resolve_dynamic_output_concept_if_needed(pipe_run_params=params)

        # Output stays Text — the override only applies when the declared output is Dynamic.
        assert pipe_llm.output.concept.code == NativeConceptCode.TEXT
        assert pipe_llm.output.concept.domain_code == SpecialDomain.NATIVE
