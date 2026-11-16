"""Store the large `Text`, `Markdown`, `Html` and `JSON` values a run receives or produces, where they are received or produced.

A text past the inline threshold, `[runtime.storage] inline_text_max_bytes`, lives in the run's storage and travels as a
reference, as an image or a document does (`pipelex.core.stuffs.stored_value_content`). The code that holds such a
value and may perform IO stores it: run setup for the run's inputs, a content-generation leaf for what it generated, a
PipeFunc's executor for what the function returned. Workflow code never stores, and neither does a dry run, whose storage
scope must never reach storage.

A value is measured on the text it is stored as: a text's or HTML's UTF-8 encoding, a JSON object's serialized form. A
value of at most the threshold stays inline; a larger one is stored under
`{storage_scope}/{leaf}/{hash}/value.{extension}`, the hash being the first 16 hexadecimal digits of the stored bytes'
SHA-256, the leaf `generated` for what the run produced and `assets` for what it received, and the extension the
content's (`txt`, `md`, `html`, `json`), so the key's last segment is a filename every reader of a storage key accepts,
the hosted platform's included. Both leaves lie under the run's storage scope, which erasing a run erases whole.

The content is turned into its reference in place (`StoredValueContent.accept_storage`), keeping the value loaded, so a
reader in the same process reads it without loading it again, and a dump of it is the reference alone.
"""

import hashlib
from collections.abc import Awaitable, Callable, Mapping
from functools import partial
from typing import Any, Final

from pipelex.config import get_config
from pipelex.core.stuffs.stored_value_content import StoredValueContent
from pipelex.core.stuffs.stored_value_walker import find_stored_value_contents
from pipelex.system.storage_scope import is_storage_scope_real
from pipelex.tools.misc.async_utils import gather_bounded
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract

# How many characters of a stored value its reference carries as its `preview`, always the value's true start.
STORED_VALUE_PREVIEW_MAX_CHARS: Final[int] = 300

# The name a stored value's file is given before its extension: `value.txt`, `value.md`, `value.html`, `value.json`.
STORED_VALUE_FILE_STEM: Final[str] = "value"

# How many values a tree of contents stores at once.
MAX_CONCURRENT_STORED_VALUE_WRITES: Final[int] = 8


def inline_text_max_bytes() -> int:
    """The most bytes a text, HTML or JSON value keeps inline, past which it is stored: `[runtime.storage] inline_text_max_bytes`."""
    return get_config().runtime.storage.inline_text_max_bytes


def make_stored_value_key(*, storage_scope: str, leaf: str, sha256_hex: str, file_extension: str) -> str:
    """The storage key of a stored value: `{storage_scope}/{leaf}/{hash}/value.{extension}`."""
    return f"{storage_scope}/{leaf}/{sha256_hex[:16]}/{STORED_VALUE_FILE_STEM}.{file_extension}"


async def store_value_if_large(
    content: StoredValueContent,
    *,
    storage_provider: StorageProviderAbstract,
    storage_scope: str,
    leaf: str,
) -> bool:
    """Store a content's inline value when it is past the inline threshold, turning the content into its reference.

    A content already holding a reference, one whose value is within the threshold, an empty value, and any content on
    a dry run's storage scope are left as they are.

    Args:
        content: The content to store, changed in place when stored.
        storage_provider: The run's storage provider.
        storage_scope: The run's storage scope, under which the value is stored.
        leaf: The leaf under the scope: `generated` for a value the run produced, `assets` for one it received.

    Returns:
        Whether the value was stored.
    """
    if content.is_stored or not is_storage_scope_real(storage_scope=storage_scope):
        return False
    stored_text = content.stored_text()
    data = stored_text.encode("utf-8")
    if not data or len(data) <= inline_text_max_bytes():
        return False
    sha256_hex = hashlib.sha256(data).hexdigest()
    key = make_stored_value_key(storage_scope=storage_scope, leaf=leaf, sha256_hex=sha256_hex, file_extension=content.stored_file_extension)
    mime_type = content.stored_mime_type
    url = await storage_provider.store(data=data, key=key, content_type=f"{mime_type}; charset=utf-8", checksum_sha256_hex=sha256_hex)
    content.accept_storage(url=url, size=len(data), mime_type=mime_type, preview=stored_text[:STORED_VALUE_PREVIEW_MAX_CHARS])
    return True


async def store_large_values(
    *,
    roots: Mapping[str, Any],
    storage_provider: StorageProviderAbstract,
    storage_scope: str,
    leaf: str,
) -> int:
    """Store every inline value past the inline threshold under the given roots, wherever it sits in them.

    A value may sit anywhere in a content: as the content itself, as an item of a list, as a field of a structure, as
    the text of a page. Each is turned into its reference in place, a bounded number at a time.

    Args:
        roots: The values to walk, each keyed by a name: a stuff's content keyed by the stuff's name, typically.
        storage_provider: The run's storage provider.
        storage_scope: The run's storage scope, under which the values are stored; a dry run's stores nothing.
        leaf: The leaf under the scope: `generated` for values the run produced, `assets` for values it received.

    Returns:
        The number of values stored.
    """
    if not is_storage_scope_real(storage_scope=storage_scope):
        return 0
    inline_contents = [found.content for found in find_stored_value_contents(roots=roots) if not found.content.is_stored]
    if not inline_contents:
        return 0
    store_factories: list[Callable[[], Awaitable[bool]]] = [
        partial(store_value_if_large, content, storage_provider=storage_provider, storage_scope=storage_scope, leaf=leaf)
        for content in inline_contents
    ]
    stored_flags = await gather_bounded(store_factories, max_concurrency=MAX_CONCURRENT_STORED_VALUE_WRITES)
    return sum(1 for is_stored in stored_flags if is_stored)
