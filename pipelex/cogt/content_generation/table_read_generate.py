"""Framework-agnostic leaf of a `PipeStructure` step that reads a spreadsheet: one table of a `Document` read into records.

The direct ``ContentGenerator`` calls it inline, and a host runtime's content generator dispatches it as a leaf operation,
an activity on Temporal, since the step may run in workflow code, which does no I/O. Only the records go back, as plain
data (`TableRecords`), never the file's bytes; the step binds them to its row concept.

The read is authorized under the run's read scope first, as every leaf does. The file's format is then judged from its
bytes, then from the media type and the name the document declares (`table_format_key_of`): anything but an Excel
workbook (`.xlsx`) or a CSV file is refused as ``input.file_type_unsupported``, naming the input. A step never
dispatches this in a dry run, which reads nothing, so there is no dry branch.
"""

from pipelex.cogt.content_generation.assignment_models import TableReadAssignment
from pipelex.cogt.content_generation.read_authorization import authorize_assignment_reads
from pipelex.config import fetch_max_bytes
from pipelex.runtime_hub import get_storage_provider
from pipelex.tools.misc.filetype_utils import UNKNOWN_FILE_TYPE, describe_file_format
from pipelex.tools.tabular.exceptions import CsvError, TableFileTypeUnsupportedError
from pipelex.tools.tabular.table_reader import locate_table_error, read_table_records, table_format_key_of, table_format_of
from pipelex.tools.tabular.table_records import TABLE_READER, TableBinding, TableRecords
from pipelex.tools.uri.uri_bytes import load_bytes_from_any_uri

# What a refusal of a file of another format says the step reads.
_TABLE_FORMATS_READ = "an Excel workbook (.xlsx) or a CSV file (.csv)"


async def read_table_of_document(*, table_read_assignment: TableReadAssignment) -> TableRecords:
    """Read the table a `PipeStructure` step names from its spreadsheet input, as records keyed by field.

    Raises:
        UriReadRefusedError: The run's read scope does not allow reading the document.
        TableFileTypeUnsupportedError: The document is neither an Excel workbook nor a CSV file.
        CsvError: The table cannot be chosen or read, or its header does not match the fields, naming the input.
        MissingDependencyError: The document is a workbook and openpyxl, the `tabular` extra, is not installed.
        RemoteFileFetchError: The document could not be fetched.
    """
    authorize_assignment_reads(job_metadata=table_read_assignment.job_metadata, uri_references=table_read_assignment.referenced_uris())
    input_name = table_read_assignment.input_name
    raw_bytes = await load_bytes_from_any_uri(
        table_read_assignment.source_uri,
        storage_provider=get_storage_provider(),
        max_bytes=fetch_max_bytes(),
    )
    format_key = table_format_key_of(raw_bytes=raw_bytes, mime_type=table_read_assignment.mime_type, file_name=table_read_assignment.file_name)
    table_format = table_format_of(format_key=format_key)
    if table_format is None:
        subject = f"Input '{input_name}'" if input_name is not None else "The document"
        described_format = (
            describe_file_format(format_key=format_key, mime_type=table_read_assignment.mime_type)
            if format_key is not None
            else "of an unknown format"
        )
        msg = f"{subject} is {described_format}: pipe '{table_read_assignment.job_metadata.pipe_code}' reads a table from {_TABLE_FORMATS_READ}."
        raise (
            TableFileTypeUnsupportedError(msg)
            .with_input(input_name=input_name)
            .with_params(format=format_key or UNKNOWN_FILE_TYPE, model=TABLE_READER)
        )
    try:
        return read_table_records(
            raw_bytes=raw_bytes,
            table_format=table_format,
            field_names=table_read_assignment.field_names,
            row_field=table_read_assignment.row_field,
            table_name=table_read_assignment.table_name,
            binding=TableBinding.STEP,
            input_name=input_name,
        )
    except CsvError as exc:
        # The codec names the file by the input it was given as; the problem names and locates the input as well.
        locate_table_error(table_error=exc, input_name=input_name)
        raise
