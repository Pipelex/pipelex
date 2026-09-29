"""Copy a file-shaped main output into the results folder, so the result opens with a double-click.

A Document or Image main output is otherwise saved only as JSON holding its URL, which for a local run is a
`pipelex-storage://` URI nobody can open. The bytes are loaded through the run's storage provider and
written beside `main_stuff.json` under the file's own name: `invoice-INV-2026-0142.pdf`, not a hash.
"""

import mimetypes
import urllib.parse
from pathlib import Path, PurePosixPath

from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.runtime_hub import get_storage_provider
from pipelex.tools.uri.uri_bytes import load_bytes_from_any_uri
from pipelex.tools.uri.uri_resolver import BASE64_DATA_URL_PREFIX

_FALLBACK_STEM = "main_stuff_file"


def _filename_from_url(url: str) -> str | None:
    if url.startswith(BASE64_DATA_URL_PREFIX):
        return None
    name = PurePosixPath(urllib.parse.urlparse(url).path).name
    return name or None


def _main_stuff_file_name(*, url: str, filename: str | None, mime_type: str | None) -> str:
    name = Path(filename).name if filename else _filename_from_url(url)
    if name:
        return name
    extension = mimetypes.guess_extension(mime_type or "") or ".bin"
    return f"{_FALLBACK_STEM}{extension}"


async def save_main_stuff_file(*, content: StuffContent, output_dir: Path) -> Path | None:
    """Write a Document or Image main output's bytes into `output_dir`, and return the file's path.

    Returns None when the content is not file-shaped. Loading can fail like any fetch, which the caller
    reports without failing the run that already succeeded.
    """
    url: str
    name: str
    match content:
        case DocumentContent():
            url = content.url
            name = _main_stuff_file_name(url=url, filename=content.filename, mime_type=content.mime_type)
        case ImageContent():
            url = content.url
            name = _main_stuff_file_name(url=url, filename=None, mime_type=content.mime_type)
        case _:
            return None
    raw_bytes = await load_bytes_from_any_uri(url, storage_provider=get_storage_provider())
    target_path = output_dir / name
    target_path.write_bytes(raw_bytes)
    return target_path
