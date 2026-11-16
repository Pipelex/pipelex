"""A run's main output that holds stored values: load them for what a person reads, or describe them.

A run's main output may hold `Text`, `Markdown`, `Html` or `JSON` values that live in storage
(`pipelex.core.stuffs.stored_value_content`), anywhere in it. What a machine reads of the output, its JSON, carries each
such value as its reference, the shape the wire carries. What a person reads of it, its Markdown, its HTML, its viewer
page and a terminal print, needs the values themselves, so the code that writes them, a hosted run's delivery of its
result files and the local `pipelex run` and `pipelex-agent run`, first loads every stored value the output holds, under
the run's read scope (`load_stored_values_of_output`). A value that cannot be loaded, such as a URL a caller gave that
no longer answers, a local file that is gone, or a key outside the run's read scope, is described by its reference
instead (`render_unloaded_output_markdown`, `render_unloaded_output_html`, `render_unloaded_output_viewer`): a run that
succeeded is never reported without its output, nor its output files left out.

The load performs IO, so only the code allowed to perform IO, a delivery and a CLI, calls it.
"""

import html

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.core.stuffs.stored_value_content import StoredValueContent
from pipelex.core.stuffs.stored_value_loader import load_stored_values
from pipelex.core.stuffs.stored_value_walker import StoredValueAtPath, find_stored_value_contents, find_unloaded_stored_values
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.log.error_fields import error_fields
from pipelex.tools.misc.json_utils import clean_json_dumps
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract

# The name each stored value's path starts with, which a refusal to load it, and the description of one not loaded, name.
OUTPUT_ROOT_NAME = "main_stuff"

# What loading a stored value can raise: the domain errors of storage, of a fetch and of decoding, an `OSError` from a
# local path that cannot be read, and a `ValueError` from a malformed data URL.
STORED_VALUE_LOAD_ERRORS: tuple[type[Exception], ...] = (PipelexError, OSError, ValueError)


def holds_stored_values(*, content: StuffContent) -> bool:
    """Whether the content holds a value in storage anywhere in it, loaded or not."""
    return any(found.content.is_stored for found in find_stored_value_contents(roots={OUTPUT_ROOT_NAME: content}))


def find_unloaded_values_of_output(*, content: StuffContent) -> list[StoredValueAtPath]:
    """The stored values the content holds that were never loaded, each with its path from `main_stuff`."""
    return find_unloaded_stored_values(roots={OUTPUT_ROOT_NAME: content})


async def load_stored_values_of_output(
    *,
    content: StuffContent,
    read_scope: str | None,
    storage_provider: StorageProviderAbstract | None,
) -> bool:
    """Load every stored value a run's output holds, under the run's read scope, and say whether all of them are now loaded.

    A value this process stored is still loaded and reads nothing. A failed load is logged with its error and leaves the
    values it did not reach as references, which the caller then describes rather than renders.

    Args:
        content: The content of the run's main output.
        read_scope: The run's read scope, ``None`` for an unscoped run, such as a local one.
        storage_provider: The storage provider that resolves a storage URI.

    Returns:
        Whether every stored value the output holds can now be read.
    """
    stored_values = find_unloaded_values_of_output(content=content)
    if not stored_values:
        return True
    try:
        await load_stored_values(stored_values=stored_values, read_scope=read_scope, storage_provider=storage_provider)
    except STORED_VALUE_LOAD_ERRORS as exc:
        # The load fails in many domain-specific ways (storage, fetch, decoding, a local path), none of which may cost a
        # successful run its output: the values left unloaded are described instead.
        log.warning("The stored values of a run's output could not all be loaded", fields=error_fields(exc=exc))
    return not find_unloaded_values_of_output(content=content)


def render_reference_form_json(*, content: StuffContent) -> str:
    """The content's JSON with each stored value as its reference, the shape the wire carries, loaded or not."""
    return clean_json_dumps(content.smart_dump(), indent=2)


def render_unloaded_output_markdown(*, content: StuffContent) -> str:
    """The Markdown a person reads of an output holding stored values that could not be loaded: what each one is, by its reference.

    An output that is itself a stored value is its description; any other lists each value not loaded by its path, then
    shows the output's JSON, each stored value as its reference.
    """
    if isinstance(content, StoredValueContent):
        return "\n\n".join(_described_lines(content=content)) + "\n"
    described_values = [
        f"- `{stored_value.path}`: {' '.join(_described_lines(content=stored_value.content))}"
        for stored_value in find_unloaded_values_of_output(content=content)
    ]
    reference_json = render_reference_form_json(content=content)
    return "The output holds stored values that were not loaded:\n\n" + "\n".join(described_values) + f"\n\n```json\n{reference_json}\n```\n"


def render_unloaded_output_html(*, content: StuffContent) -> str:
    """The HTML a person reads of an output holding stored values that could not be loaded, every text of it escaped."""
    if isinstance(content, StoredValueContent):
        return "".join(f"<p>{html.escape(line)}</p>" for line in _described_lines(content=content))
    described_values = "".join(
        f"<li><code>{html.escape(stored_value.path)}</code>: {html.escape(' '.join(_described_lines(content=stored_value.content)))}</li>"
        for stored_value in find_unloaded_values_of_output(content=content)
    )
    reference_json = html.escape(render_reference_form_json(content=content))
    return f"<p>The output holds stored values that were not loaded:</p><ul>{described_values}</ul><pre>{reference_json}</pre>"


def render_unloaded_output_viewer(*, content: StuffContent, title: str) -> str:
    """The viewer page of an output holding stored values that could not be loaded: a standalone page of its HTML description."""
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{html.escape(title)}</title>\n</head>\n<body>\n<h1>{html.escape(title)}</h1>\n"
        f"{render_unloaded_output_html(content=content)}\n</body>\n</html>\n"
    )


def _described_lines(*, content: StoredValueContent) -> list[str]:
    lines = [content.reference_summary()]
    if content.preview:
        lines.append(f"It starts: {content.preview}")
    return lines
