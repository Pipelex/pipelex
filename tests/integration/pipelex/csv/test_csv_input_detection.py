"""Integration tests pinning CSV *input detection* in ``StuffFactory`` (Phase 3).

These fence the A3/CT1 design decision — CSV input is triggered by a ``{"url": "...csv"}``
reference under a non-native structured row concept — and its documented residual:

- a non-``.csv`` ``url`` under a concept that has a ``url`` field stays a single record;
- a ``.csv`` whose rows include a ``url`` column reads correctly (the file-level ``url`` is the
  table to read; the inner ``url`` column is ordinary cell data);
- a remote ``url`` (``http(s)``/``s3``/``gs``/…) with a ``.csv`` suffix is rejected with a clear
  local-paths-only error (A1), never opened;
- the read is eager core I/O: rebuilding the working memory after the file changes on disk
  reflects the new content.
"""

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.tools.tabular.exceptions import CsvError

if TYPE_CHECKING:
    from mthds.models.pipeline_inputs import PipelineInputs

    from pipelex.core.stuffs.stuff_content import StuffContent

BUNDLE_DIR = Path(__file__).parent / "csv_demo"
LINKS_CSV = BUNDLE_DIR / "links.csv"
PEOPLE_CSV = BUNDLE_DIR / "people.csv"


class TestCsvInputDetection:
    @pytest.mark.parametrize(
        "remote_url",
        [
            "https://example.com/people.csv",
            "s3://bucket/people.csv",
            "gs://bucket/people.csv",
            # Query-string / fragment forms must still be detected as tabular and rejected: pathlib's
            # `.suffix` keeps the `?…`/`#…`, so detection must look at the URL path component, not the
            # raw string (S3 presigned URLs always carry a query string).
            "https://example.com/people.csv?token=abc",
            "s3://bucket/people.csv?X-Amz-Signature=deadbeef",
            "https://example.com/people.csv#frag",
            # A malformed port must not crash URL sanitization (the `.port` property raises): the
            # redaction must still produce a clean CsvError without leaking the token via a traceback.
            "https://example.com:bad/people.csv?token=abc",
        ],
    )
    def test_remote_csv_url_rejected(self, remote_url: str, load_test_library: Callable[[list[Path]], None]) -> None:
        load_test_library([BUNDLE_DIR])
        inputs: PipelineInputs = {"people": {"concept": "csv_demo.Person", "content": {"url": remote_url}}}
        with pytest.raises(CsvError) as exc_info:
            WorkingMemoryFactory.make_from_pipeline_inputs(inputs)
        message = str(exc_info.value)
        assert "local" in message.lower()
        # The path is preserved so the user can identify the offending input...
        assert "people.csv" in message
        # ...but the signed query string / fragment (which can carry credentials) must be stripped:
        # CsvError is caller-facing and survives STRICT disclosure, so it must not leak the token.
        for secret in ("token=abc", "X-Amz-Signature=deadbeef", "frag"):
            assert secret not in message

    def test_non_csv_url_stays_record(self, load_test_library: Callable[[list[Path]], None]) -> None:
        load_test_library([BUNDLE_DIR])
        # url field value that is NOT a tabular suffix → ordinary single record, not a CSV table.
        inputs: PipelineInputs = {"link": {"concept": "csv_demo.Link", "content": {"label": "Home", "url": "https://example.com"}}}
        working_memory = WorkingMemoryFactory.make_from_pipeline_inputs(inputs)

        content = working_memory.get_stuff("link").content
        assert not isinstance(content, ListContent)
        record = content.model_dump()
        assert record["label"] == "Home"
        assert record["url"] == "https://example.com"

    def test_record_with_csv_url_field_and_siblings_stays_record(self, load_test_library: Callable[[list[Path]], None]) -> None:
        load_test_library([BUNDLE_DIR])
        # A record that has sibling keys alongside a .csv-suffixed `url` is NOT a table reference:
        # detection is gated to the bare {"url": ...} wrapper, so the siblings are never dropped.
        inputs: PipelineInputs = {"link": {"concept": "csv_demo.Link", "content": {"label": "Home", "url": "report.csv"}}}
        working_memory = WorkingMemoryFactory.make_from_pipeline_inputs(inputs)

        content = working_memory.get_stuff("link").content
        assert not isinstance(content, ListContent)
        record = content.model_dump()
        assert record["label"] == "Home"
        assert record["url"] == "report.csv"

    def test_csv_with_url_column_reads(self, load_test_library: Callable[[list[Path]], None]) -> None:
        load_test_library([BUNDLE_DIR])
        # The file-level url ends .csv → read as a table; the inner `url` column is plain data.
        inputs: PipelineInputs = {"links": {"concept": "csv_demo.Link", "content": {"url": str(LINKS_CSV)}}}
        working_memory = WorkingMemoryFactory.make_from_pipeline_inputs(inputs)

        content = working_memory.get_stuff("links").content
        assert isinstance(content, ListContent)
        links = cast("ListContent[StuffContent]", content)
        rows = [item.model_dump() for item in links.items]
        assert [row["label"] for row in rows] == ["Home", "Docs"]
        assert [row["url"] for row in rows] == ["https://example.com", "https://example.com/docs"]

    def test_eager_read_reflects_file_mutation(self, tmp_path: Path, load_test_library: Callable[[list[Path]], None]) -> None:
        load_test_library([BUNDLE_DIR])
        people_csv = tmp_path / "people.csv"
        people_csv.write_text(PEOPLE_CSV.read_text(encoding="utf-8"), encoding="utf-8")
        inputs: PipelineInputs = {"people": {"concept": "csv_demo.Person", "content": {"url": str(people_csv)}}}

        first = WorkingMemoryFactory.make_from_pipeline_inputs(inputs)
        first_people = cast("ListContent[StuffContent]", first.get_stuff("people").content)
        assert len(first_people.items) == 3

        # Mutate the file on disk; a fresh build must re-read it (eager core I/O, not cached).
        people_csv.write_text(
            "name,job,country,birth_year,death_year\nAda Lovelace,Mathematician,United Kingdom,1815,1852\n",
            encoding="utf-8",
        )
        second = WorkingMemoryFactory.make_from_pipeline_inputs(inputs)
        second_people = cast("ListContent[StuffContent]", second.get_stuff("people").content)
        assert len(second_people.items) == 1
