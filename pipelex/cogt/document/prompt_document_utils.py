"""Utilities for preparing prompt documents for LLM APIs.

This module provides functions to convert PromptDocument instances into
PreparedFile instances that can be consumed by LLM provider APIs.
"""

import asyncio
import base64

from pipelex.cogt.document.prompt_document import (
    PromptDocument,
    PromptDocumentBase64,
    PromptDocumentBinary,
    PromptDocumentUri,
)
from pipelex.hub import get_storage_provider
from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx
from pipelex.tools.misc.file_utils import load_binary_async
from pipelex.tools.misc.filetype_utils import detect_file_type_from_base64, detect_file_type_from_bytes
from pipelex.tools.uri.prepared_file import PreparedFile, PreparedFileBase64, PreparedFileHttpUrl
from pipelex.tools.uri.resolved_uri import (
    ResolvedBase64DataUrl,
    ResolvedHttpUrl,
    ResolvedLocalPath,
    ResolvedPipelexStorage,
)


async def prepare_prompt_document(
    prompt_document: PromptDocument,
    is_http_url_enabled: bool,
) -> PreparedFile:
    """Prepare a single prompt document for LLM API consumption.

    Args:
        prompt_document: The input prompt document (URI, base64, or binary)
        is_http_url_enabled: Whether to pass HTTP URLs directly to the LLM

    Returns:
        A PreparedFile (HttpUrl or Base64) ready for the LLM API
    """
    prepared: PreparedFile
    match prompt_document:
        case PromptDocumentBase64():
            prepared = PreparedFileBase64(
                base64_data=prompt_document.base64_data,
                file_type=prompt_document.get_file_type(),
            )

        case PromptDocumentBinary():
            base64_data = base64.b64encode(prompt_document.raw_bytes).decode("ascii")
            prepared = PreparedFileBase64(
                base64_data=base64_data,
                file_type=prompt_document.get_file_type(),
            )

        case PromptDocumentUri():
            match prompt_document.resolved:
                case ResolvedHttpUrl():
                    if is_http_url_enabled:
                        prepared = PreparedFileHttpUrl(url=prompt_document.resolved.url)
                    else:
                        raw_bytes = await fetch_file_from_url_httpx(url=prompt_document.resolved.url)
                        prepared = PreparedFileBase64(
                            base64_data=base64.b64encode(raw_bytes).decode("ascii"),
                            file_type=detect_file_type_from_bytes(raw_bytes),
                        )

                case ResolvedLocalPath():
                    raw_bytes = await load_binary_async(prompt_document.resolved.path)
                    prepared = PreparedFileBase64(
                        base64_data=base64.b64encode(raw_bytes).decode("ascii"),
                        file_type=detect_file_type_from_bytes(raw_bytes),
                    )

                case ResolvedPipelexStorage():
                    storage = get_storage_provider()
                    raw_bytes = await storage.load(uri=prompt_document.resolved.storage_uri)
                    prepared = PreparedFileBase64(
                        base64_data=base64.b64encode(raw_bytes).decode("ascii"),
                        file_type=detect_file_type_from_bytes(raw_bytes),
                    )

                case ResolvedBase64DataUrl():
                    base64_data = prompt_document.resolved.base64_data
                    prepared = PreparedFileBase64(
                        base64_data=base64_data,
                        file_type=detect_file_type_from_base64(base64_data),
                    )

    return prepared


async def prep_prompt_documents(
    prompt_documents: list[PromptDocument],
    is_http_url_enabled: bool,
) -> list[PreparedFile]:
    """Prepare multiple prompt documents in parallel.

    Args:
        prompt_documents: List of input prompt documents
        is_http_url_enabled: Whether to pass HTTP URLs directly to the LLM

    Returns:
        List of PreparedFile instances ready for the LLM API
    """
    tasks = [prepare_prompt_document(prompt_document=doc, is_http_url_enabled=is_http_url_enabled) for doc in prompt_documents]
    return list(await asyncio.gather(*tasks))


async def prepare_prompt_document_as_base64(prompt_document: PromptDocument) -> PreparedFileBase64:
    """Prepare a prompt document, always returning base64-encoded data.

    This variant always fetches HTTP URLs and converts everything to base64.
    Use this when the LLM API doesn't support HTTP URLs directly.

    Args:
        prompt_document: The input prompt document (URI, base64, or binary)

    Returns:
        A PreparedFileBase64 ready for the LLM API
    """
    match prompt_document:
        case PromptDocumentBase64():
            return PreparedFileBase64(
                base64_data=prompt_document.base64_data,
                file_type=prompt_document.get_file_type(),
            )

        case PromptDocumentBinary():
            base64_data = base64.b64encode(prompt_document.raw_bytes).decode("ascii")
            return PreparedFileBase64(
                base64_data=base64_data,
                file_type=prompt_document.get_file_type(),
            )

        case PromptDocumentUri():
            match prompt_document.resolved:
                case ResolvedHttpUrl():
                    raw_bytes = await fetch_file_from_url_httpx(url=prompt_document.resolved.url)
                    return PreparedFileBase64(
                        base64_data=base64.b64encode(raw_bytes).decode("ascii"),
                        file_type=detect_file_type_from_bytes(raw_bytes),
                    )

                case ResolvedLocalPath():
                    raw_bytes = await load_binary_async(prompt_document.resolved.path)
                    return PreparedFileBase64(
                        base64_data=base64.b64encode(raw_bytes).decode("ascii"),
                        file_type=detect_file_type_from_bytes(raw_bytes),
                    )

                case ResolvedPipelexStorage():
                    storage = get_storage_provider()
                    raw_bytes = await storage.load(uri=prompt_document.resolved.storage_uri)
                    return PreparedFileBase64(
                        base64_data=base64.b64encode(raw_bytes).decode("ascii"),
                        file_type=detect_file_type_from_bytes(raw_bytes),
                    )

                case ResolvedBase64DataUrl():
                    base64_data = prompt_document.resolved.base64_data
                    return PreparedFileBase64(
                        base64_data=base64_data,
                        file_type=detect_file_type_from_base64(base64_data),
                    )
