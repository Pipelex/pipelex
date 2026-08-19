"""Usage/cost reporting reaches parity between an interpreter run and direct kernel calls.

The kernel's promise is that operator semantics have one implementation with two callers. Usage
reporting is where that promise is easiest to break silently: the records are assembled from trace
events, and a kernel call that forgot to carry a ``TraceContext`` onto its per-step ``JobMetadata``
would simply emit nothing — no error, an empty cost report, and a suite that stays green because no
test compares the two callers' output.

So this measures rather than asserts. Both sides run the same step (one LLM text generation) under
``run_mode=DRY`` with ``is_mock_usage=True``, which keeps the leaf offline while making it report
*non-zero* synthetic usage under a sentinel model. The two ``TokensUsageRecord`` lists — the wire
shape ``/execute`` returns on ``pipe_output.tokens_usages`` and durable runs persist as
``tokens_usages.json`` — are then compared field by field.

``pipe_code`` used to be the one field that legitimately differed, and it no longer does. The
interpreter stamps it on the DRY path too — ``dry_run_pipe`` identifies the pipe it is running,
exactly as ``live_run_pipe`` already did — which closed the interpreter half of KF-13 (a
``--dry-run --mock-usage`` cost report used to carry no pipe attribution at all). **The kernel tier
has since got the same fix**: ``make_step_metadata(pipe_code=…)`` names the step, so attribution
reaches the usage record on both sides and ``pipe_code`` is compared rather than excluded. Only the
timestamps differ, because the two runs happen at different times.

⚠ **Which makes the kernel side's shape load-bearing.** It calls the *ops* with a named step, the way
a compiled artifact does — not ``PipelexKernel.llm_text``. The façade is the direct-call form, where
there is no pipe because the caller did not run one, so it stays deliberately anonymous; comparing it
against an interpreter run that *did* run a pipe would compare two different situations and read the
difference as a gap. ``test_the_direct_call_facade_stays_deliberately_anonymous`` pins that half, so
neither behaviour can drift into the other unnoticed.

Transport ownership is visible in the setup itself. The interpreter half needs NDJSON tracing enabled
because its run machinery builds the event log off the config; the kernel half hands its own
``InMemoryEventLog`` to the report delegate, because for a kernel-driven run the caller owns that
lifecycle — the kernel only stamps the context it is given onto every step.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.dry_mock import MOCK_USAGE_MODEL_NAME
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.config import get_config
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.kernel.llm_ops import resolve_llm_setting_for_text, run_llm_text
from pipelex.kernel.llm_prompt_content import LlmPromptContent
from pipelex.kernel.pipelex_kernel import PipelexKernel
from pipelex.kernel.templating_style_ops import resolve_templating_style
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.reporting.reporting_types import AnyTokensUsage
from pipelex.reporting.usage_records import TokensUsageRecord, make_tokens_usage_record
from pipelex.runtime_hub import get_report_delegate
from pipelex.system.configuration.configs import NdjsonTracingConfig, TracingBackend
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.trace_context import TraceContext
from pipelex.tracing.in_memory_event_log import InMemoryEventLog
from pipelex.tracing.usage_aggregator import UsageAggregator

_DOMAIN = "kernel_usage_parity"
_PIPE_CODE = "write_text"
_USER_PROMPT = "Write about the kernel."
_MTHDS = f"""
domain = "{_DOMAIN}"
description = "One LLM text step, the smallest thing both callers can run"

[pipe.{_PIPE_CODE}]
type = "PipeLLM"
description = "Pipe that outputs plain text"
output = "Text"
prompt = "{_USER_PROMPT}"
"""

#: The record fields that carry the run's wall-clock, which two separate runs cannot share.
#: Everything else is the shape parity is measured on — ``pipe_code`` included, since the kernel tier
#: learned to name its steps.
_RUN_SPECIFIC_FIELDS = ("started_at", "completed_at")


@pytest.mark.asyncio(loop_scope="class")
class TestKernelUsageParity:
    def _comparable(self, record: TokensUsageRecord) -> dict[str, Any]:
        return {key: value for key, value in record.model_dump().items() if key not in _RUN_SPECIFIC_FIELDS}

    def _records(self, tokens_usages: list[AnyTokensUsage]) -> list[TokensUsageRecord]:
        return [make_tokens_usage_record(tokens_usage) for tokens_usage in tokens_usages]

    async def _run_through_the_interpreter(self, mocker: MockerFixture, traces_dir: str) -> list[TokensUsageRecord]:
        tracing_config = get_config().runtime.tracing
        mocker.patch.object(tracing_config, "is_enabled", True)
        mocker.patch.object(tracing_config, "backend", TracingBackend.NDJSON)
        mocker.patch.object(tracing_config, "ndjson", NdjsonTracingConfig(traces_dir=traces_dir))

        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(
            generate_graph=False,
            generate_usage=True,
        )
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, is_mock_usage=True, execution_config=execution_config)
        response = await runner.execute(pipe_code=_PIPE_CODE, mthds_contents=[_MTHDS])

        assert response.pipe_output.tokens_usages is not None, "the interpreter run assembled no usage at all"
        return self._records(response.pipe_output.tokens_usages)

    async def _run_through_the_kernel(self, *, name_the_step: bool) -> list[TokensUsageRecord]:
        """One kernel LLM step, either artifact-shaped (named) or through the façade (anonymous).

        The named arm renders the ops call the way the emitter does, rather than going through
        ``PipelexKernel.llm_text`` — that is the whole distinction the two callers of this helper
        exist to hold apart.
        """
        # The caller's transport, and the caller's lifecycle: build the event log, register it for the
        # run, read the events back, clear the registration. The kernel is handed only the context.
        event_log = InMemoryEventLog()
        trace_context = TraceContext(
            graph_id="kernel-usage-parity",
            data_inclusion=get_config().interpreter.pipeline_execution.graph.data_inclusion,
            emit_graph_events=False,
            emit_usage_events=True,
        )
        get_report_delegate().set_event_log(
            context_key=trace_context.lookup_key,
            event_log=event_log,
            workflow_id="direct",
            pipeline_run_id=trace_context.graph_id,
        )
        try:
            kernel = PipelexKernel.make(
                storage_scope="test/scope",
                run_mode=PipeRunMode.DRY,
                user_id="kernel-usage-parity",
                is_mock_usage=True,
                trace_context=trace_context,
            )
            model = LLMSetting(model="kernel-usage-parity-model", temperature=0.5)
            if name_the_step:
                llm_setting = resolve_llm_setting_for_text(llm_choice=model)
                await run_llm_text(
                    memory=WorkingMemoryFactory.make_empty(),
                    prompt_content=LlmPromptContent.make_from_text(user=_USER_PROMPT, system=None),
                    llm_setting=llm_setting,
                    concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
                    output_class=TextContent,
                    job_metadata=kernel.make_step_metadata(pipe_code=_PIPE_CODE),
                    cogt_run_params=kernel.cogt_run_params,
                    templating_style=resolve_templating_style(authored=None),
                    result_name="written",
                )
            else:
                await kernel.llm_text(
                    memory=WorkingMemoryFactory.make_empty(),
                    model=model,
                    user=_USER_PROMPT,
                    result="written",
                )
            return self._records(UsageAggregator.aggregate(event_log.read_events(trace_context.graph_id)))
        finally:
            get_report_delegate().clear_event_log(context_key=trace_context.lookup_key)

    async def test_both_callers_produce_the_same_usage_records(self, tmp_path_factory: pytest.TempPathFactory, mocker: MockerFixture) -> None:
        """One LLM step, two callers, one usage shape."""
        interpreter_records = await self._run_through_the_interpreter(mocker, str(tmp_path_factory.mktemp("traces_parity")))
        kernel_records = await self._run_through_the_kernel(name_the_step=True)

        assert len(kernel_records) == len(interpreter_records) == 1, (
            f"one LLM step must report exactly one usage record on each side, got interpreter={len(interpreter_records)} kernel={len(kernel_records)}"
        )
        assert self._comparable(kernel_records[0]) == self._comparable(interpreter_records[0])

        # Non-zero under the sentinel model on both sides: a parity of two empty records would prove
        # nothing, and zero tokens are what a plain dry run reports.
        for record in (*interpreter_records, *kernel_records):
            assert record.inference_model_name == MOCK_USAGE_MODEL_NAME
            assert sum(record.nb_tokens_by_category.values()) > 0

        # Attribution reaches the usage record on both sides, and reaches the SAME value. Stated here
        # as well as inside `_comparable` because it is the property this comparison exists for: a
        # field silently dropped from `_RUN_SPECIFIC_FIELDS` would weaken the check above in a way
        # nothing else would notice.
        assert kernel_records[0].pipe_code == interpreter_records[0].pipe_code == _PIPE_CODE

    async def test_the_direct_call_facade_stays_deliberately_anonymous(self) -> None:
        """`PipelexKernel.llm_text` names no pipe, because the caller ran none — by design, not by gap.

        Pinned so that "finish the job by naming it too" cannot land unnoticed: a façade call that
        invented a pipe code would attribute work to a pipe that never ran.
        """
        records = await self._run_through_the_kernel(name_the_step=False)

        assert len(records) == 1
        assert records[0].pipe_code is None
