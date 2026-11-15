"""Load the text behind a URL a value carries, under the run's read scope.

A `Text`, `Markdown`, `Html` or `JSON` content holds its value inline or a URL to it in storage (see
`pipelex.core.stuffs.stored_value_content`). This is the read of such a URL, beside the loaders of bytes
(`uri_bytes`): the read scope is checked first, exactly as for an image a prompt reads, so a stored key another run
owns is refused with the same `UriReadRefusedError` before any byte is read, and the bytes are then decoded as UTF-8,
the encoding every stored text is written in.

Loading performs IO, so it runs only where IO is allowed: input intake, a content-generation leaf, a PipeFunc, a
direct run. Workflow code never calls it.
"""

from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.exceptions import UriTextNotUtf8Error
from pipelex.tools.uri.uri_bytes import load_bytes_from_any_uri
from pipelex.tools.uri.uri_read_scope import authorize_uri_read


async def load_text_from_any_uri(
    uri: str,
    *,
    read_scope: str | None,
    position: str,
    storage_provider: StorageProviderAbstract | None = None,
) -> str:
    """Load the UTF-8 text a URL points at, refusing a URL the run's read scope does not allow.

    Args:
        uri: A storage URI, an HTTP(S) URL or a base64 data URL.
        read_scope: The run's read scope, ``None`` for an unscoped run, which reads everything.
        position: Where the URL sits, in the caller's words ("the text input 'pages'"), which a refusal names in place
            of the URL itself.
        storage_provider: The storage provider that resolves a storage URI, required for one.

    Returns:
        The decoded text.

    Raises:
        UriReadRefusedError: The URL is a storage key outside the read scope, or a local path, on a scoped run.
        StorageNotConfiguredError: The URL is a storage URI and no storage provider is given.
        UriTextNotUtf8Error: The bytes are not UTF-8.
    """
    authorize_uri_read(uri=uri, read_scope=read_scope, position=position)
    raw_bytes = await load_bytes_from_any_uri(uri, storage_provider=storage_provider)
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        msg = f"Could not read {position} as a text: its stored bytes are not UTF-8 ({exc.reason} at byte {exc.start})."
        raise UriTextNotUtf8Error(msg) from exc
