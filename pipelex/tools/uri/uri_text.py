"""Load the text behind a URL a value carries, under the run's read scope.

A `Text`, `Markdown`, `Html` or `JSON` content holds its value inline or a URL to it in storage (see
`pipelex.core.stuffs.stored_value_content`). This is the read of such a URL, beside the loaders of bytes
(`uri_bytes`): the read scope is checked first, exactly as for an image a prompt reads, so a stored key another run
owns is refused with the same `UriReadRefusedError` before any byte is read, and the bytes are then decoded as UTF-8,
the encoding every stored text is written in.

A text is read whole, so it is bounded by `[runtime.network] max_fetch_bytes`, the most bytes any read of a URL takes,
as a template input a `PipeDocGen` step reads is: a stored object is sized before it is read, a data URL by the length
of its text, and an http(s) URL's body as the fetch streams it.

Loading performs IO, so it runs only where IO is allowed: input intake, a content-generation leaf, a PipeFunc, a
direct run. Workflow code never calls it.
"""

from pipelex.config import fetch_max_bytes
from pipelex.tools.misc.file_fetch_utils import fetching_for_input
from pipelex.tools.storage.exceptions import StorageNotConfiguredError
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.exceptions import UriTextNotUtf8Error, UriTextTooLargeError
from pipelex.tools.uri.resolved_uri import ResolvedBase64DataUrl, ResolvedHttpUrl, ResolvedLocalPath, ResolvedPipelexStorage
from pipelex.tools.uri.uri_bytes import load_bytes_from_any_uri
from pipelex.tools.uri.uri_read_scope import authorize_uri_read
from pipelex.tools.uri.uri_resolver import resolve_uri


async def load_text_from_any_uri(
    uri: str,
    *,
    read_scope: str | None,
    position: str,
    storage_provider: StorageProviderAbstract | None = None,
    input_name: str | None = None,
) -> str:
    """Load the UTF-8 text a URL points at, refusing a URL the run's read scope does not allow, or past the read cap.

    Args:
        uri: A storage URI, an HTTP(S) URL or a base64 data URL.
        read_scope: The run's read scope, ``None`` for an unscoped run, which reads everything.
        position: Where the URL sits, in the caller's words ("the text input 'pages'"), which a refusal names in place
            of the URL itself.
        storage_provider: The storage provider that resolves a storage URI, required for one.
        input_name: The input whose value the URL is, when the reader knows it, which a refusal of the text names.

    Returns:
        The decoded text.

    Raises:
        UriReadRefusedError: The URL is a storage key outside the read scope, or a local path, on a scoped run.
        StorageNotConfiguredError: The URL is a storage URI and no storage provider is given.
        UriTextTooLargeError: The stored object or the data URL is past `[runtime.network] max_fetch_bytes`.
        RemoteFileTooLargeError: The http(s) URL serves more than that cap.
        UriTextNotUtf8Error: The bytes are not UTF-8.
    """
    authorize_uri_read(uri=uri, read_scope=read_scope, position=position)
    max_bytes = fetch_max_bytes()
    size = await _text_size(uri=uri, storage_provider=storage_provider)
    if size is not None and size > max_bytes:
        msg = f"Could not read {position}: it is {size} bytes, past the {max_bytes} bytes a text is read up to."
        raise UriTextTooLargeError(msg, limit=max_bytes, size=size, input_name=input_name)
    with fetching_for_input(input_name=input_name):
        raw_bytes = await load_bytes_from_any_uri(uri, storage_provider=storage_provider, max_bytes=max_bytes)
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        msg = f"Could not read {position} as a text: its stored bytes are not UTF-8 ({exc.reason} at byte {exc.start})."
        raise UriTextNotUtf8Error(msg, input_name=input_name) from exc


async def _text_size(*, uri: str, storage_provider: StorageProviderAbstract | None) -> int | None:
    """The size of the text behind a URL, read without its bytes, or ``None`` when the read bounds itself or cannot size it.

    A stored object is sized by its provider, a data URL by the decoded length its base64 text tells. An http(s) URL's
    fetch bounds its own body, and a local path, which only an unscoped run reads, is left to the load.

    Raises:
        StorageNotConfiguredError: The URL is a storage URI and no storage provider is given.
    """
    resolved_uri = resolve_uri(uri)
    match resolved_uri:
        case ResolvedPipelexStorage():
            if storage_provider is None:
                msg = f"Cannot load a pipelex-storage:// URI without a storage provider: {uri}"
                raise StorageNotConfiguredError(msg)
            return await storage_provider.load_size(resolved_uri.storage_uri)
        case ResolvedBase64DataUrl():
            return len(resolved_uri.base64_data) * 3 // 4
        case ResolvedHttpUrl() | ResolvedLocalPath():
            return None
