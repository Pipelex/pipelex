import json
import socket

import pytest
from pytest_mock import MockerFixture, MockType

from pipelex.base_exceptions import ErrorDomain, ErrorReport
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction, UserActionKind
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.exceptions import WorkingMemoryStuffNotFoundError
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_run.delivery_assignment import (
    DeliveryAssignment,
    DeliveryStatus,
    StorageTarget,
    WebhookTarget,
)
from pipelex.pipe_run.delivery_executor import DeliveryExecutor
from pipelex.pipe_run.exceptions import PipeJobError, StorageDeliveryError, WebhookDeliveryError
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.network.exceptions import SsrfBlockedError


def _make_main_stuff() -> Stuff:
    return Stuff(
        stuff_code="main-code",
        stuff_name="main_stuff",
        concept=Concept(
            code="Text",
            domain_code="native",
            description="Plain text",
            structure_class_name="TextContent",
        ),
        content=TextContent(text="Hello delivery!"),
    )


def _make_output_mock(mocker: MockerFixture) -> MockType:
    """A PipeOutput stand-in with the usage fields defaulted to None, like a run with usage assembly off."""
    mock_output: MockType = mocker.MagicMock()
    mock_output.tokens_usages = None
    mock_output.usage_assembly_error = None
    return mock_output


@pytest.mark.asyncio(loop_scope="class")
class TestDeliveryExecutor:
    async def test_execute_storage_only(self, mocker: MockerFixture) -> None:
        mock_storage = mocker.AsyncMock()
        mock_storage.store = mocker.AsyncMock(return_value="pipelex-storage://test-key")
        mock_storage.public_url = mocker.Mock(return_value="file:///tmp/results/plr-123")
        mocker.patch("pipelex.pipe_run.delivery_executor.get_storage_provider", return_value=mock_storage)

        mock_output = _make_output_mock(mocker)
        mock_output.working_memory_raw = None
        mock_output.working_memory.smart_dump.return_value = {"root": {}, "aliases": {}}
        mock_output.working_memory.resolve_main_stuff.return_value = _make_main_stuff()
        mock_output.graph_spec = None

        executor = DeliveryExecutor()
        assignment = DeliveryAssignment(storage=StorageTarget())

        await executor.execute(
            pipe_output=mock_output,
            user_id="test-user",
            pipeline_run_id="plr-123",
            delivery_assignment=assignment,
            status=DeliveryStatus.COMPLETED,
        )

        mock_storage.store.assert_called()
        stored_keys = [call.kwargs["key"] for call in mock_storage.store.call_args_list]
        assert any("test-user/plr-123/working_memory.json" in key for key in stored_keys)
        # A completed run always delivers a main stuff, so the main_stuff artifact files are always written.
        assert any("test-user/plr-123/main_stuff.json" in key for key in stored_keys)
        assert any("test-user/plr-123/main_stuff.md" in key for key in stored_keys)
        assert any("test-user/plr-123/main_stuff.html" in key for key in stored_keys)
        assert any("test-user/plr-123/tokens_usages.json" in key for key in stored_keys)

    async def test_execute_webhook_only(self, mocker: MockerFixture) -> None:
        mock_client = mocker.AsyncMock()
        mock_response = mocker.MagicMock()
        mock_response.raise_for_status = mocker.Mock()
        mock_client.__aenter__ = mocker.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mocker.AsyncMock(return_value=False)
        mock_client.post = mocker.AsyncMock(return_value=mock_response)
        mocker.patch("pipelex.pipe_run.delivery_executor.httpx.AsyncClient", return_value=mock_client)

        executor = DeliveryExecutor()
        assignment = DeliveryAssignment(
            webhooks=[WebhookTarget(url="https://example.com/callback")],
        )

        await executor.execute(
            pipe_output=None,
            user_id="test-user",
            pipeline_run_id="plr-456",
            delivery_assignment=assignment,
            status=DeliveryStatus.COMPLETED,
        )

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs["json"]
        assert payload["pipeline_run_id"] == "plr-456"
        assert payload["state"] == "COMPLETED"
        # Transitional legacy spelling rides along for one release (master D1/D7).
        assert payload["status"] == "COMPLETED"
        assert "result_url" not in payload

    async def test_execute_webhook_with_custom_payload(self, mocker: MockerFixture) -> None:
        mock_client = mocker.AsyncMock()
        mock_response = mocker.MagicMock()
        mock_response.raise_for_status = mocker.Mock()
        mock_client.__aenter__ = mocker.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mocker.AsyncMock(return_value=False)
        mock_client.post = mocker.AsyncMock(return_value=mock_response)
        mocker.patch("pipelex.pipe_run.delivery_executor.httpx.AsyncClient", return_value=mock_client)

        executor = DeliveryExecutor()
        assignment = DeliveryAssignment(
            webhooks=[WebhookTarget(url="https://example.com", payload={"custom": "data"})],
        )

        await executor.execute(
            pipe_output=None,
            user_id="test-user",
            pipeline_run_id="plr-789",
            delivery_assignment=assignment,
            status=DeliveryStatus.FAILED,
        )

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["status"] == "FAILED"
        assert payload["custom"] == "data"

    async def test_execute_no_storage_on_failure(self, mocker: MockerFixture) -> None:
        """Storage should be skipped when pipe_output is None (failure case)."""
        mock_storage = mocker.AsyncMock()
        mocker.patch("pipelex.pipe_run.delivery_executor.get_storage_provider", return_value=mock_storage)

        executor = DeliveryExecutor()
        assignment = DeliveryAssignment(storage=StorageTarget())

        await executor.execute(
            pipe_output=None,
            user_id="test-user",
            pipeline_run_id="plr-fail",
            delivery_assignment=assignment,
            status=DeliveryStatus.FAILED,
        )

        mock_storage.store.assert_not_called()

    async def test_execute_empty_assignment(self) -> None:
        """Empty assignment should do nothing without errors."""
        executor = DeliveryExecutor()
        assignment = DeliveryAssignment()

        await executor.execute(
            pipe_output=None,
            user_id="test-user",
            pipeline_run_id="plr-noop",
            delivery_assignment=assignment,
            status=DeliveryStatus.COMPLETED,
        )

    async def test_storage_failure_raises(self, mocker: MockerFixture) -> None:
        mock_storage = mocker.AsyncMock()
        mock_storage.store = mocker.AsyncMock(side_effect=Exception("S3 down"))
        mocker.patch("pipelex.pipe_run.delivery_executor.get_storage_provider", return_value=mock_storage)

        mock_output = _make_output_mock(mocker)
        mock_output.working_memory_raw = None
        mock_output.working_memory.smart_dump.return_value = {}
        mock_output.working_memory.resolve_main_stuff.return_value = _make_main_stuff()
        mock_output.graph_spec = None

        executor = DeliveryExecutor()
        assignment = DeliveryAssignment(storage=StorageTarget())

        with pytest.raises(StorageDeliveryError):
            await executor.execute(
                pipe_output=mock_output,
                user_id="test-user",
                pipeline_run_id="plr-err",
                delivery_assignment=assignment,
                status=DeliveryStatus.COMPLETED,
            )

    async def test_generate_result_files_raises_without_main_stuff_typed(self, mocker: MockerFixture) -> None:
        """A completed run always resolves its declared output — a typed working memory with neither
        a main stuff nor a recorded absence is a contract violation, not an empty envelope.
        """
        mock_output = _make_output_mock(mocker)
        mock_output.working_memory_raw = None
        mock_output.working_memory = WorkingMemory()
        mock_output.graph_spec = None

        with pytest.raises(WorkingMemoryStuffNotFoundError):
            await DeliveryExecutor().generate_result_files(mock_output)

    async def test_generate_result_files_raises_without_main_stuff_raw(self, mocker: MockerFixture) -> None:
        """Same contract on the raw (cross-process) path: neither a raw main stuff nor a recorded absence fails loudly."""
        mock_output = _make_output_mock(mocker)
        mock_output.working_memory_raw = {"root": {}, "aliases": {}}
        mock_output.graph_spec = None

        with pytest.raises(PipeJobError):
            await DeliveryExecutor().generate_result_files(mock_output)

    async def test_generate_result_files_absent_main_typed(self, mocker: MockerFixture) -> None:
        """An absent main output is a first-class success: the typed arm delivers an explicit
        absence artifact (main_stuff.json/md/html) instead of raising.
        """
        working_memory = WorkingMemory()
        working_memory.record_new_main_absence(
            AbsenceRecord(
                variable_name="penalty_summary",
                kind=AbsenceKind.DECLARED_ABSENT,
                reason="no penalty clause found in this contract",
                producing_pipe="check_penalty_clause",
            ),
        )
        mock_output = _make_output_mock(mocker)
        mock_output.working_memory_raw = None
        mock_output.working_memory = working_memory
        mock_output.graph_spec = None

        files = await DeliveryExecutor().generate_result_files(mock_output)

        assert "working_memory.json" in files
        json_text = files["main_stuff.json"].data.decode("utf-8")
        assert '"absent": true' in json_text
        assert "no penalty clause found in this contract" in json_text
        assert "check_penalty_clause" in json_text
        md_text = files["main_stuff.md"].data.decode("utf-8")
        assert "absent" in md_text.lower()
        assert "no penalty clause found in this contract" in md_text
        assert "main_stuff.html" in files

    async def test_generate_result_files_absent_main_raw(self, mocker: MockerFixture) -> None:
        """Same on the raw (cross-process) path: a recorded main absence in the raw ledger delivers
        the absence artifact instead of the contract-violation error.
        """
        mock_output = _make_output_mock(mocker)
        mock_output.working_memory_raw = {
            "root": {},
            "aliases": {},
            "absences": {
                "main_stuff": {
                    "variable_name": "penalty_summary",
                    "kind": "skipped",
                    "reason": "skipped because input 'penalty_clause' is absent",
                    "producing_pipe": "summarize_penalty",
                    "upstream": None,
                },
            },
        }
        mock_output.graph_spec = None

        files = await DeliveryExecutor().generate_result_files(mock_output)

        json_text = files["main_stuff.json"].data.decode("utf-8")
        assert '"absent": true' in json_text
        assert "skipped because input 'penalty_clause' is absent" in json_text
        md_text = files["main_stuff.md"].data.decode("utf-8")
        assert "summarize_penalty" in md_text
        assert "main_stuff.html" in files

    async def test_generate_result_files_writes_usage_artifact_with_records(self, mocker: MockerFixture) -> None:
        """The tokens_usages.json artifact carries the run's usage in the client wire shape
        (``TokensUsageRecord``): computed ``cost``, no ``unit_costs``, no ``job_metadata`` —
        so a durable client reads costs from the polled result files alone.
        """
        mock_output = _make_output_mock(mocker)
        mock_output.working_memory_raw = None
        mock_output.working_memory.smart_dump.return_value = {"root": {}, "aliases": {}}
        mock_output.working_memory.resolve_main_stuff.return_value = _make_main_stuff()
        mock_output.graph_spec = None
        mock_output.tokens_usages = [
            LLMTokensUsage(
                model_type="llm",
                job_metadata=JobMetadata(user_id="test-user", pipeline_run_id="plr-usage"),
                inference_model_name="test-model",
                inference_model_id="test-model-id",
                nb_tokens_by_category={TokenCategory.INPUT: 15, TokenCategory.OUTPUT: 4},
                unit_costs={CostCategory.INPUT: 3.0, CostCategory.OUTPUT: 15.0},
            )
        ]

        files = await DeliveryExecutor().generate_result_files(mock_output)

        assert files["tokens_usages.json"].content_type == "application/json"
        usage_doc = json.loads(files["tokens_usages.json"].data.decode("utf-8"))
        assert usage_doc["usage_assembly_error"] is None
        records = usage_doc["tokens_usages"]
        assert len(records) == 1
        record = records[0]
        assert record["model_type"] == "llm"
        assert record["inference_model_name"] == "test-model"
        assert record["inference_model_id"] == "test-model-id"
        assert record["nb_tokens_by_category"] == {"input": 15, "output": 4}
        assert record["cost"] == 15 * (3.0 / 1_000_000) + 4 * (15.0 / 1_000_000)
        assert "unit_costs" not in record
        assert "job_metadata" not in record

    async def test_generate_result_files_usage_artifact_null_when_usage_off(self, mocker: MockerFixture) -> None:
        """A run with usage assembly off still writes the artifact with explicit nulls, so a
        durable client can tell "usage off for this run" (file present, null) from "run
        delivered before the artifact existed" (file absent).
        """
        mock_output = _make_output_mock(mocker)
        mock_output.working_memory_raw = None
        mock_output.working_memory.smart_dump.return_value = {"root": {}, "aliases": {}}
        mock_output.working_memory.resolve_main_stuff.return_value = _make_main_stuff()
        mock_output.graph_spec = None

        files = await DeliveryExecutor().generate_result_files(mock_output)

        usage_doc = json.loads(files["tokens_usages.json"].data.decode("utf-8"))
        assert usage_doc == {"tokens_usages": None, "usage_assembly_error": None}

    async def test_generate_result_files_usage_artifact_carries_assembly_error(self, mocker: MockerFixture) -> None:
        """A failed usage assembly surfaces on the artifact instead of silently reading as "usage off"."""
        mock_output = _make_output_mock(mocker)
        mock_output.working_memory_raw = None
        mock_output.working_memory.smart_dump.return_value = {"root": {}, "aliases": {}}
        mock_output.working_memory.resolve_main_stuff.return_value = _make_main_stuff()
        mock_output.graph_spec = None
        mock_output.usage_assembly_error = "usage event read failed"

        files = await DeliveryExecutor().generate_result_files(mock_output)

        usage_doc = json.loads(files["tokens_usages.json"].data.decode("utf-8"))
        assert usage_doc == {"tokens_usages": None, "usage_assembly_error": "usage event read failed"}

    async def test_try_local_hydrate_stuff_returns_typed_for_builtin(self) -> None:
        from pipelex.core.stuffs.text_content import TextContent  # noqa: PLC0415
        from pipelex.hub import get_class_registry  # noqa: PLC0415

        registry = get_class_registry()
        if not registry.has_class(name="TextContent"):
            registry.register_class(TextContent)

        stuff_raw = {
            "stuff_code": "test",
            "stuff_name": "greeting",
            "concept": {
                "code": "Text",
                "domain_code": "native",
                "description": "Plain text",
                "structure_class_name": "TextContent",
            },
            "content": {"text": "Hello!"},
        }

        result = DeliveryExecutor.try_local_hydrate_stuff(stuff_raw)

        assert result is not None
        assert isinstance(result.content, TextContent)
        assert result.content.text == "Hello!"

    async def test_try_local_hydrate_stuff_returns_none_for_missing_class(self, mocker: MockerFixture) -> None:
        from pipelex import log as pipelex_log  # noqa: PLC0415

        warn_spy = mocker.spy(pipelex_log, "warning")

        stuff_raw = {
            "stuff_code": "test",
            "stuff_name": "x",
            "concept": {
                "code": "Greeting",
                "domain_code": "dynamic_test",
                "description": "Dynamic concept",
                "structure_class_name": "dynamic_test__Greeting",
            },
            "content": {"message": "hi"},
        }

        result = DeliveryExecutor.try_local_hydrate_stuff(stuff_raw)

        assert result is None
        assert warn_spy.call_count == 1
        assert "Local hydration failed" in str(warn_spy.call_args)

    async def test_try_local_hydrate_stuff_returns_none_for_malformed_dict(self, mocker: MockerFixture) -> None:
        from pipelex import log as pipelex_log  # noqa: PLC0415

        warn_spy = mocker.spy(pipelex_log, "warning")

        stuff_raw: dict[str, object] = {"stuff_code": "test", "content": {"text": "x"}}

        result = DeliveryExecutor.try_local_hydrate_stuff(stuff_raw)

        assert result is None
        assert warn_spy.call_count == 1

    async def test_raw_fallback_html_escapes_special_chars(self, mocker: MockerFixture) -> None:
        """Fallback HTML rendering must escape HTML-special chars to prevent XSS.

        json.dumps does not escape <, >, or &, so a pipeline output containing
        "</pre><script>..." would break out of the <pre> wrapper and execute
        as live HTML when the stored result file is fetched.
        """
        mock_output = _make_output_mock(mocker)
        mock_output.working_memory_raw = {
            "root": {
                "main_stuff": {
                    "stuff_code": "main_stuff",
                    "concept": {
                        "code": "Unknown",
                        "domain_code": "dynamic_test",
                        "description": "Dynamic concept not registered locally",
                        "structure_class_name": "dynamic_test__Unknown",
                    },
                    "content": {"payload": "</pre><script>alert(1)</script><pre>"},
                }
            },
            "aliases": {},
        }
        mock_output.graph_spec = None

        files = await DeliveryExecutor().generate_result_files(mock_output)

        html_text = files["main_stuff.html"].data.decode("utf-8")
        assert html_text.startswith("<pre>")
        assert html_text.endswith("</pre>")
        # The injected closing tag must be escaped, not present as live HTML inside the wrapper.
        inner = html_text[len("<pre>") : -len("</pre>")]
        assert "</pre>" not in inner
        assert "<script>" not in inner
        assert "&lt;/pre&gt;" in html_text
        assert "&lt;script&gt;" in html_text

        # JSON file must still contain the unescaped raw content (it's not HTML).
        json_text = files["main_stuff.json"].data.decode("utf-8")
        assert "</pre><script>alert(1)</script><pre>" in json_text

    async def test_generate_result_files_with_pydantic_instances_in_raw(self, mocker: MockerFixture) -> None:
        """working_memory_raw can contain hydrated Pydantic instances after Temporal transit.

        When `dump_for_transport()` runs in a child workflow, it embeds `__class__` metadata
        on ListContent items so the parent can reconstruct them. Kajson's Temporal data
        converter then eagerly rehydrates those dicts back into BaseModel instances on the
        activity worker that runs delivery — even though the typed slot is `dict[str, Any]`.

        `clean_json_dumps()` does not know how to serialize a Pydantic BaseModel, so the
        delivery activity blows up with `TypeError: Object of type PageContent is not JSON
        serializable`. This test pins that scenario.
        """
        from pipelex.core.stuffs.image_content import ImageContent  # noqa: PLC0415
        from pipelex.core.stuffs.page_content import PageContent  # noqa: PLC0415
        from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent  # noqa: PLC0415
        from pipelex.core.stuffs.text_content import TextContent  # noqa: PLC0415

        page = PageContent(
            text_and_images=TextAndImagesContent(
                text=TextContent(text="Page 1 contents"),
                images=[ImageContent(url="https://example.com/img.png")],
            ),
        )

        mock_output = _make_output_mock(mocker)
        mock_output.working_memory_raw = {
            "root": {
                "cv_pages": {
                    "stuff_code": "cv_pages",
                    "stuff_name": "cv_pages",
                    "concept": {
                        "code": "Page",
                        "domain_code": "native",
                        "description": "A page",
                        "structure_class_name": "PageContent",
                    },
                    "content": [page],
                }
            },
            "aliases": {"main_stuff": "cv_pages"},
        }
        mock_output.graph_spec = None

        files = await DeliveryExecutor().generate_result_files(mock_output)

        json_text = files["working_memory.json"].data.decode("utf-8")
        assert "Page 1 contents" in json_text
        assert "https://example.com/img.png" in json_text

    async def test_webhook_includes_error_report_on_failed_status(self, mocker: MockerFixture) -> None:
        """A FAILED delivery with an ``ErrorReport`` includes a VERBOSE ``error`` dict the receiver can rehydrate."""
        mock_client = mocker.AsyncMock()
        mock_response = mocker.MagicMock()
        mock_response.raise_for_status = mocker.Mock()
        mock_client.__aenter__ = mocker.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mocker.AsyncMock(return_value=False)
        mock_client.post = mocker.AsyncMock(return_value=mock_response)
        mocker.patch("pipelex.pipe_run.delivery_executor.httpx.AsyncClient", return_value=mock_client)

        error_report = ErrorReport(
            error_type="LLMCompletionError",
            message="provider returned 429",
            title="AI inference failed",
            type_uri="https://docs.pipelex.com/latest/errors/llm-completion-error/",
            error_category="transient",
            error_domain=ErrorDomain.RUNTIME,
            retryable=True,
            user_action=UserAction(kind=UserActionKind.WAIT_AND_RETRY, detail="Wait a moment and retry"),
            model="gpt-4o-mini",
            provider="openai",
            provider_metadata=ProviderErrorMetadata(
                provider=ProviderName.OPENAI,
                sdk_exception_type="RateLimitError",
                message="429 Too Many Requests",
                status_code=429,
                retry_after_seconds=2.5,
            ),
        )

        executor = DeliveryExecutor()
        assignment = DeliveryAssignment(webhooks=[WebhookTarget(url="https://example.com/callback")])

        await executor.execute(
            pipe_output=None,
            user_id="test-user",
            pipeline_run_id="plr-failed",
            delivery_assignment=assignment,
            status=DeliveryStatus.FAILED,
            error_report=error_report,
        )

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["status"] == DeliveryStatus.FAILED
        assert "error" in payload, "FAILED webhook must include the structured error report"
        rehydrated = ErrorReport.from_dict(payload["error"])
        assert rehydrated == error_report, "VERBOSE payload must round-trip through from_dict"

    async def test_webhook_omits_error_when_report_is_none(self, mocker: MockerFixture) -> None:
        """A completed delivery (no report) must not introduce an ``error`` field in the payload."""
        mock_client = mocker.AsyncMock()
        mock_response = mocker.MagicMock()
        mock_response.raise_for_status = mocker.Mock()
        mock_client.__aenter__ = mocker.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mocker.AsyncMock(return_value=False)
        mock_client.post = mocker.AsyncMock(return_value=mock_response)
        mocker.patch("pipelex.pipe_run.delivery_executor.httpx.AsyncClient", return_value=mock_client)

        executor = DeliveryExecutor()
        assignment = DeliveryAssignment(webhooks=[WebhookTarget(url="https://example.com/callback")])

        await executor.execute(
            pipe_output=None,
            user_id="test-user",
            pipeline_run_id="plr-success",
            delivery_assignment=assignment,
            status=DeliveryStatus.COMPLETED,
        )

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["status"] == DeliveryStatus.COMPLETED
        assert "error" not in payload

    async def test_webhook_omits_error_when_failed_status_with_none_report(self, mocker: MockerFixture) -> None:
        """A FAILED delivery with ``error_report=None`` must not introduce an ``error`` field in the payload.

        The COMPLETED case is pinned by ``test_webhook_omits_error_when_report_is_none``,
        but the FAILED case is not — a future regression defaulting ``error`` to ``{}``
        on FAILED would slip through. ``_notify_webhook`` only writes
        ``payload["error"]`` when ``error_report is not None``, regardless of status.
        """
        mock_client = mocker.AsyncMock()
        mock_response = mocker.MagicMock()
        mock_response.raise_for_status = mocker.Mock()
        mock_client.__aenter__ = mocker.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mocker.AsyncMock(return_value=False)
        mock_client.post = mocker.AsyncMock(return_value=mock_response)
        mocker.patch("pipelex.pipe_run.delivery_executor.httpx.AsyncClient", return_value=mock_client)

        executor = DeliveryExecutor()
        assignment = DeliveryAssignment(webhooks=[WebhookTarget(url="https://example.com/callback")])

        await executor.execute(
            pipe_output=None,
            user_id="test-user",
            pipeline_run_id="plr-failed-no-report",
            delivery_assignment=assignment,
            status=DeliveryStatus.FAILED,
            error_report=None,
        )

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["status"] == DeliveryStatus.FAILED
        assert "error" not in payload

    async def test_storage_completion_log_includes_request_id_when_set(self, mocker: MockerFixture) -> None:
        """The ``Storage delivery completed`` log line carries the originating ``request_id`` for cross-phase correlation."""
        from pipelex import log as pipelex_log  # noqa: PLC0415

        info_spy = mocker.spy(pipelex_log, "info")

        mock_storage = mocker.AsyncMock()
        mock_storage.store = mocker.AsyncMock(return_value="pipelex-storage://test-key")
        mocker.patch("pipelex.pipe_run.delivery_executor.get_storage_provider", return_value=mock_storage)

        mock_output = _make_output_mock(mocker)
        mock_output.working_memory_raw = None
        mock_output.working_memory.smart_dump.return_value = {"root": {}, "aliases": {}}
        mock_output.working_memory.resolve_main_stuff.return_value = _make_main_stuff()
        mock_output.graph_spec = None

        executor = DeliveryExecutor()
        assignment = DeliveryAssignment(storage=StorageTarget())

        await executor.execute(
            pipe_output=mock_output,
            user_id="test-user",
            pipeline_run_id="plr-storage-req",
            delivery_assignment=assignment,
            status=DeliveryStatus.COMPLETED,
            request_id="req-abc-123",
        )

        storage_messages = [str(c.args[0]) for c in info_spy.call_args_list if "Storage delivery completed" in str(c.args[0])]
        assert storage_messages, "Storage delivery completion must emit one info log"
        assert "request_id=req-abc-123" in storage_messages[0]
        assert "pipeline_run_id=plr-storage-req" in storage_messages[0]

    async def test_webhook_completion_log_includes_request_id_when_set(self, mocker: MockerFixture) -> None:
        """The ``Webhook delivery completed`` log line carries the originating ``request_id`` for cross-phase correlation."""
        from pipelex import log as pipelex_log  # noqa: PLC0415

        info_spy = mocker.spy(pipelex_log, "info")

        mock_client = mocker.AsyncMock()
        mock_response = mocker.MagicMock()
        mock_response.raise_for_status = mocker.Mock()
        mock_client.__aenter__ = mocker.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mocker.AsyncMock(return_value=False)
        mock_client.post = mocker.AsyncMock(return_value=mock_response)
        mocker.patch("pipelex.pipe_run.delivery_executor.httpx.AsyncClient", return_value=mock_client)

        executor = DeliveryExecutor()
        assignment = DeliveryAssignment(webhooks=[WebhookTarget(url="https://example.com/callback")])

        await executor.execute(
            pipe_output=None,
            user_id="test-user",
            pipeline_run_id="plr-webhook-req",
            delivery_assignment=assignment,
            status=DeliveryStatus.COMPLETED,
            request_id="req-xyz-789",
        )

        webhook_messages = [str(c.args[0]) for c in info_spy.call_args_list if "Webhook delivery completed" in str(c.args[0])]
        assert webhook_messages, "Webhook delivery completion must emit one info log"
        assert "request_id=req-xyz-789" in webhook_messages[0]
        assert "pipeline_run_id=plr-webhook-req" in webhook_messages[0]

    async def test_failed_webhook_log_includes_request_id_when_set(self, mocker: MockerFixture) -> None:
        """``request_id`` and ``error_report`` are independent dimensions of ``DeliveryExecutor.execute``.

        The COMPLETED variant is pinned by ``test_webhook_completion_log_includes_request_id_when_set``;
        this pins that the FAILED + populated-error_report path still surfaces ``request_id`` on the
        delivery log line — so a future refactor that split the FAILED and COMPLETED webhook code
        paths cannot drop the correlation id from the failure surface.
        """
        from pipelex import log as pipelex_log  # noqa: PLC0415

        info_spy = mocker.spy(pipelex_log, "info")

        mock_client = mocker.AsyncMock()
        mock_response = mocker.MagicMock()
        mock_response.raise_for_status = mocker.Mock()
        mock_client.__aenter__ = mocker.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mocker.AsyncMock(return_value=False)
        mock_client.post = mocker.AsyncMock(return_value=mock_response)
        mocker.patch("pipelex.pipe_run.delivery_executor.httpx.AsyncClient", return_value=mock_client)

        error_report = ErrorReport(
            error_type="LLMCompletionError",
            message="provider returned 429",
            title="AI inference failed",
            type_uri="https://docs.pipelex.com/latest/errors/llm-completion-error/",
            error_category="transient",
            error_domain=ErrorDomain.RUNTIME,
            retryable=True,
            user_action=UserAction(kind=UserActionKind.WAIT_AND_RETRY, detail="Wait a moment and retry"),
            model="gpt-4o-mini",
            provider="openai",
            provider_metadata=ProviderErrorMetadata(
                provider=ProviderName.OPENAI,
                sdk_exception_type="RateLimitError",
                message="429 Too Many Requests",
                status_code=429,
                retry_after_seconds=2.5,
            ),
        )

        executor = DeliveryExecutor()
        assignment = DeliveryAssignment(webhooks=[WebhookTarget(url="https://example.com/callback")])

        await executor.execute(
            pipe_output=None,
            user_id="test-user",
            pipeline_run_id="plr-webhook-failed-req",
            delivery_assignment=assignment,
            status=DeliveryStatus.FAILED,
            error_report=error_report,
            request_id="req-fail-1",
        )

        webhook_messages = [str(c.args[0]) for c in info_spy.call_args_list if "Webhook delivery completed" in str(c.args[0])]
        assert webhook_messages, "Webhook delivery completion must emit one info log even on FAILED status"
        assert "request_id=req-fail-1" in webhook_messages[0]
        assert "pipeline_run_id=plr-webhook-failed-req" in webhook_messages[0]

    async def test_completion_logs_omit_request_id_when_unset(self, mocker: MockerFixture) -> None:
        """When ``request_id`` is None (run dispatched without an inbound id), the log lines do NOT print a stray ``request_id=None``."""
        from pipelex import log as pipelex_log  # noqa: PLC0415

        info_spy = mocker.spy(pipelex_log, "info")

        mock_client = mocker.AsyncMock()
        mock_response = mocker.MagicMock()
        mock_response.raise_for_status = mocker.Mock()
        mock_client.__aenter__ = mocker.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mocker.AsyncMock(return_value=False)
        mock_client.post = mocker.AsyncMock(return_value=mock_response)
        mocker.patch("pipelex.pipe_run.delivery_executor.httpx.AsyncClient", return_value=mock_client)

        executor = DeliveryExecutor()
        assignment = DeliveryAssignment(webhooks=[WebhookTarget(url="https://example.com/callback")])

        await executor.execute(
            pipe_output=None,
            user_id="test-user",
            pipeline_run_id="plr-no-req",
            delivery_assignment=assignment,
            status=DeliveryStatus.COMPLETED,
        )

        webhook_messages = [str(c.args[0]) for c in info_spy.call_args_list if "Webhook delivery completed" in str(c.args[0])]
        assert webhook_messages, "Webhook delivery completion must emit one info log"
        assert "request_id" not in webhook_messages[0], "an unset request_id must not produce a stray field"

    async def test_webhook_aborts_on_dns_rebind_to_private_ip(self, mocker: MockerFixture) -> None:
        """A callback host that passes literal-IP validation but resolves to a private
        address at delivery time must abort with ``SsrfBlockedError`` — the DNS-rebinding
        guard. The error is a security signal and propagates (it is NOT re-wrapped as a
        ``WebhookDeliveryError``), so the delivery aborts loudly rather than POSTing to an
        internal service. This drives the real ``SsrfGuardedTransport`` (httpx.AsyncClient
        is deliberately NOT mocked here) and aborts before any socket opens.
        """

        def fake_getaddrinfo(*_args: object, **_kwargs: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
            return [(int(socket.AF_INET), int(socket.SOCK_STREAM), 6, "", ("169.254.169.254", 80))]

        mocker.patch("socket.getaddrinfo", side_effect=fake_getaddrinfo)

        executor = DeliveryExecutor()
        assignment = DeliveryAssignment(webhooks=[WebhookTarget(url="http://attacker.example/cb")])

        with pytest.raises(SsrfBlockedError):
            await executor.execute(
                pipe_output=None,
                user_id="test-user",
                pipeline_run_id="plr-ssrf",
                delivery_assignment=assignment,
                status=DeliveryStatus.COMPLETED,
            )

    async def test_webhook_failure_raises(self, mocker: MockerFixture) -> None:
        import httpx  # noqa: PLC0415

        mock_client = mocker.AsyncMock()
        mock_client.__aenter__ = mocker.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mocker.AsyncMock(return_value=False)
        mock_client.post = mocker.AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mocker.patch("pipelex.pipe_run.delivery_executor.httpx.AsyncClient", return_value=mock_client)

        executor = DeliveryExecutor()
        assignment = DeliveryAssignment(
            webhooks=[WebhookTarget(url="https://down.example.com")],
        )

        with pytest.raises(WebhookDeliveryError):
            await executor.execute(
                pipe_output=None,
                user_id="test-user",
                pipeline_run_id="plr-err",
                delivery_assignment=assignment,
                status=DeliveryStatus.COMPLETED,
            )
