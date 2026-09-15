import httpx
import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipeline.input_reachability import Reachability, RemoteInputRef, collect_remote_input_refs, probe_remote_inputs

REF = RemoteInputRef(variable_name="doc", url="https://example.com/file.pdf")


def _answering(status_code: int) -> httpx.MockTransport:
    return httpx.MockTransport(lambda _request: httpx.Response(status_code))


def _raising(exc: httpx.RequestError) -> httpx.MockTransport:
    def _handler(_request: httpx.Request) -> httpx.Response:
        raise exc

    return httpx.MockTransport(_handler)


@pytest.mark.asyncio(loop_scope="class")
class TestInputReachability:
    def test_collects_remote_urls_on_documents_images_and_lists_only(self) -> None:
        stuffs = [
            StuffFactory.make_stuff(
                concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.DOCUMENT),
                content=DocumentContent(url="https://example.com/a.pdf"),
                name="doc",
            ),
            StuffFactory.make_stuff(
                concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
                content=ImageContent(url="pipelex-storage://bucket/b.png"),
                name="stored_image",
            ),
            StuffFactory.make_stuff(
                concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
                content=ListContent(items=[ImageContent(url="http://example.com/c.png"), ImageContent(url="data:image/png;base64,xx")]),
                name="images",
            ),
            StuffFactory.make_stuff(
                concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
                content=TextContent(text="https://example.com/not-a-resource"),
                name="text",
            ),
        ]
        memory = WorkingMemoryFactory.make_from_multiple_stuffs(stuffs)

        refs = collect_remote_input_refs(working_memory=memory)

        assert refs == [
            RemoteInputRef(variable_name="doc", url="https://example.com/a.pdf"),
            RemoteInputRef(variable_name="images", url="http://example.com/c.png"),
        ]

    @pytest.mark.parametrize(
        ("status_code", "expected"),
        [
            pytest.param(200, Reachability.REACHABLE, id="ok"),
            pytest.param(302, Reachability.REACHABLE, id="redirect-without-follow"),
            pytest.param(404, Reachability.UNREACHABLE, id="not-found"),
            pytest.param(410, Reachability.UNREACHABLE, id="gone"),
            pytest.param(401, Reachability.UNKNOWN, id="auth-wall"),
            pytest.param(429, Reachability.UNKNOWN, id="rate-limited"),
            pytest.param(500, Reachability.UNKNOWN, id="server-error"),
        ],
    )
    async def test_status_code_verdicts(self, status_code: int, expected: Reachability) -> None:
        """A dead resource is unreachable; a blocked or broken host is unknown, never refused."""
        report = await probe_remote_inputs(refs=[REF], timeout_seconds=1, transport=_answering(status_code))

        assert report.verdicts[0].reachability is expected
        assert f"HTTP {status_code}" in report.verdicts[0].reason

    async def test_head_rejection_falls_back_to_ranged_get(self) -> None:
        """A host answering 403/405 to HEAD gets one ranged GET, whose status decides."""
        seen: list[tuple[str, str | None]] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.method, request.headers.get("Range")))
            return httpx.Response(405 if request.method == "HEAD" else 206)

        report = await probe_remote_inputs(refs=[REF], timeout_seconds=1, transport=httpx.MockTransport(_handler))

        assert seen == [("HEAD", None), ("GET", "bytes=0-0")]
        assert report.verdicts[0].reachability is Reachability.REACHABLE

    @pytest.mark.parametrize(
        ("exc", "expected", "reason"),
        [
            pytest.param(httpx.ConnectError("dns"), Reachability.UNREACHABLE, "could not be reached", id="connect"),
            pytest.param(httpx.ReadTimeout("slow"), Reachability.UNKNOWN, "did not answer in time", id="timeout"),
            pytest.param(httpx.RemoteProtocolError("bad"), Reachability.UNKNOWN, "probe failed", id="protocol"),
        ],
    )
    async def test_network_failure_verdicts(self, exc: httpx.RequestError, expected: Reachability, reason: str) -> None:
        report = await probe_remote_inputs(refs=[REF], timeout_seconds=1, transport=_raising(exc))

        assert report.verdicts[0].reachability is expected
        assert reason in report.verdicts[0].reason

    async def test_no_refs_makes_no_request(self) -> None:
        def _handler(_request: httpx.Request) -> httpx.Response:
            msg = "no request expected"
            raise AssertionError(msg)

        report = await probe_remote_inputs(refs=[], timeout_seconds=1, transport=httpx.MockTransport(_handler))

        assert report.verdicts == []
