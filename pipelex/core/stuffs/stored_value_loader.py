"""Load the value a `Text`, `Markdown`, `Html` or `JSON` content keeps in storage.

The content classes perform no IO (`pipelex.core.stuffs.stored_value_content`), so the read lives here, imported only
by code allowed to perform IO: input intake, a content-generation leaf, a PipeFunc, a direct run. Workflow code never
loads. The read goes through `load_text_from_any_uri`, which checks the run's read scope first, so a key outside it is
refused with the `UriReadRefusedError` an image read raises, before any byte is read.
"""

from pipelex.core.stuffs.stored_value_content import StoredValueContent
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.uri_text import load_text_from_any_uri


async def load_stored_value(
    content: StoredValueContent,
    *,
    read_scope: str | None,
    position: str,
    storage_provider: StorageProviderAbstract | None = None,
) -> None:
    """Load a content's stored value once, under the run's read scope, and keep it on the content.

    The content's fields are left unchanged, so a dump of it is still its reference. A content holding its value
    inline, or already loaded, reads nothing. Once loaded, the value reads synchronously (`require_text`,
    `require_inner_html`, `require_json_obj`, every `rendered_*` method).

    Args:
        content: The content whose value to load.
        read_scope: The run's read scope, ``None`` for an unscoped run.
        position: Where the value sits, in the caller's words ("the text input 'pages'"), which a refusal names.
        storage_provider: The storage provider that resolves a storage URI, required for one.

    Raises:
        UriReadRefusedError: The URL is outside the run's read scope, or a local path, on a scoped run.
        StorageNotConfiguredError: The URL is a storage URI and no storage provider is given.
        UriTextNotUtf8Error: The stored bytes are not UTF-8.
        StoredValueUnreadableError: The stored text is not a value of the content's kind.
    """
    if content.url is None or content.is_loaded:
        return
    text = await load_text_from_any_uri(content.url, read_scope=read_scope, position=position, storage_provider=storage_provider)
    content.accept_loaded_text(text=text)
