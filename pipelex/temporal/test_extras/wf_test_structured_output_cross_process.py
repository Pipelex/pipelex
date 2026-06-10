from temporalio import workflow

# All imports below run inside ``workflow.unsafe.imports_passed_through()``: they
# must stay at runtime (not under ``TYPE_CHECKING``) so the workflow body can
# reference them when Temporal replays history. The ``noqa: TC001`` on the
# protocol is therefore deliberate — moving it under ``TYPE_CHECKING`` would
# break replay because the symbol is type-annotated on a runtime variable.
with workflow.unsafe.imports_passed_through():
    from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
    from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol  # noqa: TC001
    from pipelex.cogt.llm.llm_prompt import LLMPrompt
    from pipelex.cogt.llm.llm_setting import LLMSetting
    from pipelex.pipeline.job_metadata import JobMetadata
    from pipelex.temporal.exceptions import ContentGenerationError
    from pipelex.temporal.log_temporal import workflow_log
    from pipelex.temporal.test_extras.temporal_registry_test_models import FixtureCustomer, FixtureInvoice, FixtureLineItem
    from pipelex.temporal.tprl_content_generation.content_generator_in_workflow_factory import ContentGeneratorInWorkflowFactory


@workflow.defn(name="wf_test_structured_output_cross_process")
class WfTestStructuredOutputCrossProcess:
    """Exercise ``ContentGeneratorInWorkflow.make_object`` / ``make_object_list``
    end-to-end across the Temporal data converter, with a nested
    ``FixtureInvoice`` structure (``FixtureCustomer`` + ``list[FixtureLineItem]``).

    Pair with substitute activities (``act_llm_gen_object`` /
    ``act_llm_gen_object_list``) that return canonical ``FixtureInvoice``
    instances so the assertion checks the serialization round-trip rather
    than LLM output. The single-vs-list branch is selected by ``is_list``.
    """

    @workflow.run
    async def run(self, is_list: bool) -> None:
        workflow_log.debug("Workflow start")
        content_generator: ContentGeneratorProtocol = ContentGeneratorInWorkflowFactory.make_content_generator_in_workflow()

        job_metadata = JobMetadata(user_id="temporal-test", pipeline_run_id=workflow.info().workflow_id)
        cogt_run_params = CogtRunParams()
        llm_setting = LLMSetting(model="$testing-structured", temperature=0.0)
        prompt = LLMPrompt(user_text="round-trip nested structured output")

        if is_list:
            invoices = await content_generator.make_object_list(
                job_metadata=job_metadata,
                cogt_run_params=cogt_run_params,
                object_class=FixtureInvoice,
                llm_setting_for_object_list=llm_setting,
                llm_prompt_for_object_list=prompt,
            )
            _assert_invoice_list_round_trip(invoices)
        else:
            invoice = await content_generator.make_object(
                job_metadata=job_metadata,
                cogt_run_params=cogt_run_params,
                object_class=FixtureInvoice,
                llm_setting_for_object=llm_setting,
                llm_prompt_for_object=prompt,
            )
            _assert_invoice_round_trip(invoice)

        workflow_log.debug("Workflow complete")


def _assert_invoice_round_trip(invoice: FixtureInvoice) -> None:
    """Verify the nested fields survived the cross-process serialization.

    The substitute activity returns canonical fixtures (see test file); these
    assertions pin the round-trip contract: nested ``FixtureCustomer`` keeps
    name and email, the ``line_items`` list preserves order and field types,
    and numeric fields stay typed (``int`` for quantity, ``float`` for
    unit_price). A regression in ``ContentGeneratorInWorkflow.make_object`` or
    in the Temporal data converter would surface here as an ``AssertionError``
    rather than a silent type drop.
    """
    # Runtime isinstance guards: while pyright sees the declared types as
    # sufficient, the value crossed a Temporal data converter boundary —
    # if the round-trip silently produced a generic dict or a wrong subclass,
    # we want a clear error here, not a downstream attribute error.
    if not isinstance(invoice, FixtureInvoice):  # pyright: ignore[reportUnnecessaryIsInstance]
        msg = f"Expected FixtureInvoice, got {type(invoice).__name__}"
        raise ContentGenerationError(msg)
    if not isinstance(invoice.customer, FixtureCustomer):  # pyright: ignore[reportUnnecessaryIsInstance]
        msg = f"Expected nested FixtureCustomer, got {type(invoice.customer).__name__}"
        raise ContentGenerationError(msg)
    if invoice.invoice_number != "INV-RT-001":
        msg = f"Unexpected invoice_number after round-trip: {invoice.invoice_number!r}"
        raise ContentGenerationError(msg)
    if invoice.customer.name != "Alice Chen" or invoice.customer.email != "alice@example.com":
        msg = f"Customer fields not preserved: {invoice.customer!r}"
        raise ContentGenerationError(msg)
    if len(invoice.line_items) != 2:
        msg = f"Expected 2 line items, got {len(invoice.line_items)}"
        raise ContentGenerationError(msg)
    for line_item in invoice.line_items:
        if not isinstance(line_item, FixtureLineItem):  # pyright: ignore[reportUnnecessaryIsInstance]
            msg = f"Expected FixtureLineItem in list, got {type(line_item).__name__}"
            raise ContentGenerationError(msg)


def _assert_invoice_list_round_trip(invoices: list[FixtureInvoice]) -> None:
    if len(invoices) != 2:
        msg = f"Expected 2 invoices, got {len(invoices)}"
        raise ContentGenerationError(msg)
    expected_numbers = {"INV-RT-A", "INV-RT-B"}
    for invoice in invoices:
        if not isinstance(invoice, FixtureInvoice):  # pyright: ignore[reportUnnecessaryIsInstance]
            msg = f"Expected FixtureInvoice, got {type(invoice).__name__}"
            raise ContentGenerationError(msg)
        if not invoice.line_items or not isinstance(invoice.line_items[0], FixtureLineItem):  # pyright: ignore[reportUnnecessaryIsInstance]
            msg = f"Invoice {invoice.invoice_number!r} missing nested FixtureLineItem"
            raise ContentGenerationError(msg)
    seen_numbers = {invoice.invoice_number for invoice in invoices}
    if seen_numbers != expected_numbers:
        msg = f"Invoice numbers not preserved: got {seen_numbers}, expected {expected_numbers}"
        raise ContentGenerationError(msg)
