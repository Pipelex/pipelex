"""Load the value a `Text`, `Markdown`, `Html` or `JSON` content keeps in storage.

The content classes perform no IO (`pipelex.core.stuffs.stored_value_content`), so the read lives here, imported only
by code allowed to perform IO: input intake, a content-generation leaf, a PipeFunc, a direct run. Workflow code never
loads. The read goes through `load_text_from_any_uri`, which checks the run's read scope first, so a key outside it is
refused with the `UriReadRefusedError` an image read raises, before any byte is read.

`load_stored_values` loads every value a tree of contents holds, as `find_unloaded_stored_values`
(`pipelex.core.stuffs.stored_value_walker`) found them: what a content-generation leaf does before it renders a prompt.
The reads overlap, at most `MAX_CONCURRENT_URI_READS` at a time, so a list of many stored pages does not open as many
reads at once.

A stored value that cannot be read as one of its kind is a URL a caller or a method pointed at the wrong file, so each
refusal is an input's (`input.file_unreadable`, `input.too_large`), naming the stuff whose value it is.
"""

from collections.abc import Awaitable, Callable, Sequence
from functools import partial

from pipelex.core.stuffs.exceptions import StoredValueUnreadableError
from pipelex.core.stuffs.stored_value_content import StoredValueContent
from pipelex.core.stuffs.stored_value_walker import StoredValueAtPath
from pipelex.tools.misc.async_utils import gather_bounded
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.uri_bytes import MAX_CONCURRENT_URI_READS
from pipelex.tools.uri.uri_text import load_text_from_any_uri


async def load_stored_value(
    content: StoredValueContent,
    *,
    read_scope: str | None,
    position: str,
    storage_provider: StorageProviderAbstract | None = None,
    input_name: str | None = None,
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
        input_name: The stuff whose value it is, when the caller knows it, which a refusal names as its input.

    Raises:
        UriReadRefusedError: The URL is outside the run's read scope, or a local path, on a scoped run.
        StorageNotConfiguredError: The URL is a storage URI and no storage provider is given.
        UriTextTooLargeError: The stored value is past `[runtime.network] max_fetch_bytes`.
        UriTextNotUtf8Error: The stored bytes are not UTF-8.
        StoredValueUnreadableError: The stored text is not a value of the content's kind.
    """
    if content.url is None or content.is_loaded:
        return
    text = await load_text_from_any_uri(
        content.url, read_scope=read_scope, position=position, storage_provider=storage_provider, input_name=input_name
    )
    try:
        content.accept_loaded_text(text=text)
    except StoredValueUnreadableError as exc:
        exc.with_input(input_name=input_name)
        raise


async def load_stored_values(
    *,
    stored_values: Sequence[StoredValueAtPath],
    read_scope: str | None,
    storage_provider: StorageProviderAbstract | None = None,
) -> None:
    """Load each of the stored values found in a tree of contents, a bounded number at a time, each refusal naming its path.

    Args:
        stored_values: The values to load, as `find_unloaded_stored_values` lists them.
        read_scope: The run's read scope, ``None`` for an unscoped run.
        storage_provider: The storage provider that resolves a storage URI, required for one.

    Raises:
        UriReadRefusedError: A URL is outside the run's read scope, or a local path, on a scoped run.
        StorageNotConfiguredError: A URL is a storage URI and no storage provider is given.
        UriTextTooLargeError: A stored value is past `[runtime.network] max_fetch_bytes`.
        UriTextNotUtf8Error: The stored bytes of a value are not UTF-8.
        StoredValueUnreadableError: The stored text of a value is not a value of its content's kind.
    """
    if not stored_values:
        return
    load_factories: list[Callable[[], Awaitable[None]]] = [
        partial(
            load_stored_value,
            stored_value.content,
            read_scope=read_scope,
            position=stored_value.position,
            storage_provider=storage_provider,
            input_name=stored_value.input_name,
        )
        for stored_value in stored_values
    ]
    await gather_bounded(load_factories, max_concurrency=MAX_CONCURRENT_URI_READS)
