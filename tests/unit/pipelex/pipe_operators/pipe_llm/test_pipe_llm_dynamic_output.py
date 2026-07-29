"""Unit tests for `PipeLLM.resolve_dynamic_output_stuff_spec`.

When a PipeLLM declares `output = "Dynamic"`, the actual output concept is supplied
at run time via `pipe_run_params.dynamic_output_concept_ref` (or the legacy
`params[DYNAMIC_OUTPUT_CONCEPT]` key). The resolver returns a fresh `StuffSpec` with
the resolved concept, leaving `self.output` unchanged so the same pipe instance can
be reused across runs with different overrides.

Pinned behaviors:

- explicit override (qualified ref or bare code) → returned StuffSpec carries that concept
- no override → fallback `native.Text`
- non-Dynamic output → returns `self.output` unchanged
- `self.output.concept` is **never mutated** (regression guard for the cubic P1 bug
  where the resolver mutated state, making the second run on the same instance
  silently ignore a different `dynamic_output_concept_ref`)
"""

from typing import Callable

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain import SpecialDomain
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_run.pipe_run_params import PipeRunParamKey
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory


def _make_pipe(domain_code: str, pipe_code: str, output: str) -> PipeLLM:
    blueprint = PipeLLMBlueprint(
        description="dynamic-output test pipe",
        inputs={"user_text": "native.Text"},
        output=output,
        prompt="Process $user_text",
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
        """Regression: when the run params provide no override, the resolver still
        returns a StuffSpec carrying `native.Text` (previously, the fallback was
        only assigned to a local variable, so downstream code ran with `Dynamic`
        and the LLM's structured JSON deserialized to `{}`).
        """
        load_empty_library()
        pipe_llm = _make_pipe(domain_code="test_domain", pipe_code="test_dyn_fallback", output="native.Dynamic")
        params = PipeRunParamsFactory.make_run_params()  # no dynamic_output_concept_ref

        resolved = pipe_llm.resolve_dynamic_output_stuff_spec(pipe_run_params=params)

        assert resolved.concept.code == NativeConceptCode.TEXT
        assert resolved.concept.domain_code == SpecialDomain.NATIVE
        # self.output is untouched.
        assert pipe_llm.output.concept.code == NativeConceptCode.DYNAMIC
        assert pipe_llm.output.concept.domain_code == SpecialDomain.NATIVE

    def test_override_with_qualified_native_ref(
        self,
        load_empty_library: Callable[[], str],
    ):
        load_empty_library()
        pipe_llm = _make_pipe(domain_code="test_domain", pipe_code="test_dyn_qualified", output="native.Dynamic")
        params = PipeRunParamsFactory.make_run_params(dynamic_output_concept_ref="native.Number")

        resolved = pipe_llm.resolve_dynamic_output_stuff_spec(pipe_run_params=params)

        assert resolved.concept.code == NativeConceptCode.NUMBER
        assert resolved.concept.domain_code == SpecialDomain.NATIVE
        assert pipe_llm.output.concept.code == NativeConceptCode.DYNAMIC

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

        resolved = pipe_llm.resolve_dynamic_output_stuff_spec(pipe_run_params=params)

        assert resolved.concept.code == NativeConceptCode.NUMBER
        assert resolved.concept.domain_code == SpecialDomain.NATIVE

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

        resolved = pipe_llm.resolve_dynamic_output_stuff_spec(pipe_run_params=params)

        assert resolved.concept.code == NativeConceptCode.NUMBER
        assert resolved.concept.domain_code == SpecialDomain.NATIVE

    def test_non_dynamic_output_is_unchanged(
        self,
        load_empty_library: Callable[[], str],
    ):
        load_empty_library()
        pipe_llm = _make_pipe(domain_code="test_domain", pipe_code="test_dyn_non_dynamic", output="native.Text")
        params = PipeRunParamsFactory.make_run_params(dynamic_output_concept_ref="native.Number")

        resolved = pipe_llm.resolve_dynamic_output_stuff_spec(pipe_run_params=params)

        # Non-Dynamic output: helper returns the static spec unchanged, ignoring the override.
        assert resolved is pipe_llm.output
        assert resolved.concept.code == NativeConceptCode.TEXT
        assert resolved.concept.domain_code == SpecialDomain.NATIVE

    def test_resolves_independently_across_invocations(
        self,
        load_empty_library: Callable[[], str],
    ):
        """Regression for the cubic P1: the same pipe instance must resolve a different
        dynamic output concept on each call. The previous implementation mutated
        `self.output.concept` on the first call, so the guard at the top of the helper
        (which short-circuits when concept is no longer Dynamic) silently ignored every
        subsequent override.
        """
        load_empty_library()
        pipe_llm = _make_pipe(domain_code="test_domain", pipe_code="test_dyn_repeat", output="native.Dynamic")

        first = pipe_llm.resolve_dynamic_output_stuff_spec(
            pipe_run_params=PipeRunParamsFactory.make_run_params(dynamic_output_concept_ref="native.Number"),
        )
        assert first.concept.code == NativeConceptCode.NUMBER
        # self.output stays Dynamic between runs.
        assert pipe_llm.output.concept.code == NativeConceptCode.DYNAMIC

        second = pipe_llm.resolve_dynamic_output_stuff_spec(
            pipe_run_params=PipeRunParamsFactory.make_run_params(dynamic_output_concept_ref="native.Text"),
        )
        assert second.concept.code == NativeConceptCode.TEXT
        # First call's resolution didn't leak into the second.
        assert first.concept.code == NativeConceptCode.NUMBER
        assert pipe_llm.output.concept.code == NativeConceptCode.DYNAMIC
