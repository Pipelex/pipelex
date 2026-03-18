from typing import Any
from urllib.parse import urlparse

from linkup import LinkupClient, LinkupFetchResponse
from typing_extensions import override

from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_output import ExtractedImageFromPage, ExtractOutput, Page
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.hub import get_secrets_provider
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.image_utils import ImageFormat

_EXTENSION_TO_MIME: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _mime_type_from_url(url: str) -> str | None:
    """Infer MIME type from URL extension; returns None for unsupported formats."""
    path = urlparse(url).path.lower()
    for extension, mime in _EXTENSION_TO_MIME.items():
        if path.endswith(extension):
            return mime
    return None


def _is_valid_image_url(url: str) -> bool:
    """Check if a URL is a well-formed absolute HTTP(S) URL."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    # Detect malformed URLs where a protocol-relative path was appended to a base domain
    # e.g. "https://example.com//cdn.other.com/image.png"
    return not parsed.path.startswith("//")


class LinkupExtractWorker(ExtractWorkerAbstract):
    def __init__(
        self,
        extra_config: dict[str, Any],
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ) -> None:
        ExtractWorkerAbstract.__init__(
            self,
            extra_config=extra_config,
            inference_model=inference_model,
            reporting_delegate=reporting_delegate,
        )
        api_key = get_secrets_provider().get_secret(secret_id="LINKUP_API_KEY")
        self._linkup_client = LinkupClient(api_key=api_key)

    @override
    async def _extract_pages(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        document_uri = extract_job.extract_input.document_uri
        if not document_uri:
            msg = "LinkupExtractWorker requires a document_uri (web URL) in ExtractInput"
            raise ValueError(msg)

        job_params = extract_job.job_params
        extract_images = (job_params.max_nb_images or 0) != 0

        response: LinkupFetchResponse = await self._linkup_client.async_fetch(
            url=document_uri,
            render_js=job_params.render_js,
            include_raw_html=job_params.include_raw_html,
            extract_images=extract_images,
        )

        # Per-request cost model: costs are defined per million, so 1 request = 1_000_000
        if extract_tokens_usage := extract_job.job_report.extract_tokens_usage:
            extract_tokens_usage.nb_tokens_by_category = {
                TokenCategory.INPUT: 1_000_000,
                TokenCategory.OUTPUT: 1_000_000,
            }

        max_images = job_params.max_nb_images
        extracted_images: list[ExtractedImageFromPage] = []
        if response.images:
            for image in response.images:
                if max_images is not None and len(extracted_images) >= max_images:
                    break
                if not _is_valid_image_url(image.url):
                    continue
                mime_type = _mime_type_from_url(image.url)
                if mime_type is None or not ImageFormat.is_supported_mime_type(mime_type):
                    continue
                extracted_images.append(
                    ExtractedImageFromPage(
                        size=None,
                        actual_url=image.url,
                        mime_type=mime_type,
                        caption=image.alt or None,
                    )
                )

        page = Page(
            text=response.markdown,
            raw_html=response.raw_html,
            extracted_images=extracted_images,
        )

        return ExtractOutput(pages={0: page})
