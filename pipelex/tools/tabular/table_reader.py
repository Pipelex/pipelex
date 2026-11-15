"""Reading a table file into records, whatever its format: the format's judgment, the codec's dispatch, and the local shortcut.

Two callers read tables:

- **A `PipeStructure` step** whose input is a `Document`, through the content generator's `read_table` leaf
  (`pipelex.cogt.content_generation.table_read_generate`), which loads the file's bytes and calls `read_table_records`
  under the step's binding.
- **A run input**, a local `{"url": "....csv"}` or `.xlsx` given for a structured list input, which `StuffFactory` reads at
  run setup with `list_content_from_table_file` under the run input's binding.

The format is judged from the file's bytes first, then from its media type, then from its name (`table_format_of`), the
order every other format check applies (`identify_mime_type`), so a workbook stored as `application/octet-stream` is
still a workbook, and a CSV file, which no bytes identify, is known by its declared type or its name.
"""

from pathlib import Path

from pipelex.config import table_reading_limits
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContentType
from pipelex.errors.error_codes import error_code_spec
from pipelex.tools.misc.filetype_utils import format_key_from_mime_type, guess_file_type_from_bytes, identify_mime_type, mime_type_of_file_name
from pipelex.tools.tabular.csv_codec import csv_subject, flat_field_names, list_content_from_csv, read_csv_raw_table
from pipelex.tools.tabular.exceptions import CsvError, CsvReadError, TableSelectionError
from pipelex.tools.tabular.table_reading_config import TableReadingConfig
from pipelex.tools.tabular.table_records import (
    RawTable,
    TableBinding,
    TableFormat,
    TableRecords,
    build_table_records,
    list_content_from_table_records,
)
from pipelex.tools.tabular.xlsx_codec import is_xlsx_archive, read_xlsx_raw_table, xlsx_subject

# The type a sniffer gives a zip archive whose contents it does not recognise, and the format key it has.
_BARE_ZIP_MIME_TYPE = "application/zip"
_BARE_ZIP_FORMAT_KEY = "zip"


def table_format_key_of(*, raw_bytes: bytes, mime_type: str | None, file_name: str | None) -> str | None:
    """The format key of a file, judged from its bytes, then its media type, then its name; None when nothing tells.

    A CSV file carries no signature its bytes could be identified by, and is often declared with a type that names no
    table format: `application/octet-stream`, `text/plain`, or `application/vnd.ms-excel`, the type Windows gives a
    `.csv` file when Excel is installed. So when the bytes identify nothing and the declared type names no format a
    table is read from, the file's name decides, when it names one.

    A workbook whose identifying entry is not among its archive's first few sniffs as a bare zip, which neither a type
    naming no format nor a missing name settles: its archive is opened then, and a workbook is known by its parts
    (`is_xlsx_archive`).
    """
    identified_mime_type = identify_mime_type(head=raw_bytes, declared_mime_type=mime_type, file_name=file_name)
    if identified_mime_type is None and file_name:
        identified_mime_type = mime_type_of_file_name(file_name=file_name)
    format_key = format_key_from_mime_type(mime_type=identified_mime_type)
    if table_format_of(format_key=format_key) is not None:
        return format_key
    sniffed_file_type = guess_file_type_from_bytes(raw_bytes=raw_bytes)
    # A bare zip whose type and name tell nothing more, or tell only that it is a zip, is judged by its parts.
    is_unsettled = format_key is None or format_key == _BARE_ZIP_FORMAT_KEY
    if sniffed_file_type is not None and sniffed_file_type.mime == _BARE_ZIP_MIME_TYPE and is_unsettled and is_xlsx_archive(raw_bytes=raw_bytes):
        return TableFormat.XLSX
    if not file_name or sniffed_file_type is not None:
        return format_key
    named_table_format = table_format_named_by(file_name=file_name)
    return named_table_format if named_table_format is not None else format_key


def table_format_named_by(*, file_name: str) -> TableFormat | None:
    """The table format a file's name names by its extension, None for a name naming another format or none."""
    return table_format_of(format_key=format_key_from_mime_type(mime_type=mime_type_of_file_name(file_name=file_name)))


def table_format_of(*, format_key: str | None) -> TableFormat | None:
    """The table format a format key names, None for any other format, or for an unknown one."""
    if format_key is None:
        return None
    try:
        return TableFormat(format_key)
    except ValueError:
        return None


def table_subject(*, table_format: TableFormat, input_name: str | None) -> str:
    """How a message names a table file: by its format and the input it was given as, never by its path."""
    match table_format:
        case TableFormat.CSV:
            return csv_subject(input_name=input_name)
        case TableFormat.XLSX:
            return xlsx_subject(input_name=input_name)


def read_table_records(
    *,
    raw_bytes: bytes,
    table_format: TableFormat,
    field_names: list[str],
    row_field: str | None,
    table_name: str | None,
    binding: TableBinding,
    limits: TableReadingConfig,
    input_name: str | None,
) -> TableRecords:
    """Read a table file's bytes into records keyed by the fields their columns match.

    Args:
        raw_bytes: The file's bytes.
        table_format: The file's format.
        field_names: The fields of the row concept, which must be flat.
        row_field: The field that receives each row's position, which no column may match; None for none.
        table_name: The Excel Table to read; None for a workbook's only Table, and always None for a CSV file.
        binding: Whose rules the table is read under.
        limits: How large a workbook, and a Table, may be read.
        input_name: The input the file was given as, which messages name it by.

    Raises:
        TableSelectionError: A Table is named for a CSV file, or the workbook's Table cannot be chosen.
        CsvError: The file cannot be read, or its header does not match the fields.
        MissingDependencyError: The file is a workbook and openpyxl is not installed.
        TableTooLargeError: The workbook, its Table, or the CSV file is larger than `limits` allow.
    """
    subject = table_subject(table_format=table_format, input_name=input_name)
    raw_table: RawTable
    match table_format:
        case TableFormat.CSV:
            if table_name is not None:
                msg = f"The step reads the Table '{table_name}', and {subject} has no Tables: give an Excel workbook (.xlsx) holding that Table."
                raise TableSelectionError(msg)
            raw_table = read_csv_raw_table(raw_bytes=raw_bytes, binding=binding, limits=limits, subject=subject)
        case TableFormat.XLSX:
            raw_table = read_xlsx_raw_table(raw_bytes=raw_bytes, table_name=table_name, limits=limits, subject=subject)
    return build_table_records(
        raw_table=raw_table,
        table_format=table_format,
        field_names=field_names,
        row_field=row_field,
        binding=binding,
        subject=subject,
    )


def list_content_from_table_file(
    *,
    path: Path,
    row_model: type[StuffContentType],
    input_name: str | None,
) -> ListContent[StuffContentType]:
    """Read a local `.csv` or `.xlsx` file given as a run input into a `ListContent` of `row_model`, one row per item.

    Under the run input's binding: every column must match a field. A workbook is read from its only Table, since a run
    input names none. The format is told by the path's suffix, as the input hook detected it.

    Raises:
        CsvError: The file cannot be read, its header does not match the fields, or a value cannot be converted.
        MissingDependencyError: The file is a workbook and openpyxl is not installed.
    """
    if path.suffix.lower() != ".xlsx":
        return list_content_from_csv(path, row_model=row_model, input_name=input_name)
    field_names = flat_field_names(row_model)
    subject = xlsx_subject(input_name=input_name)
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        msg = f"Could not read {subject}: {exc.strerror or type(exc).__name__}"
        raise CsvReadError(msg) from exc
    table_records = read_table_records(
        raw_bytes=raw_bytes,
        table_format=TableFormat.XLSX,
        field_names=field_names,
        row_field=None,
        table_name=None,
        binding=TableBinding.RUN_INPUT,
        limits=table_reading_limits(),
        input_name=input_name,
    )
    return list_content_from_table_records(
        table_records=table_records, row_model=row_model, row_field=None, binding=TableBinding.RUN_INPUT, subject=subject
    )


def locate_table_error(*, table_error: CsvError, input_name: str | None) -> CsvError:
    """Name, on a table refusal, the input the file came from, and the input itself as the field when nothing narrower is known.

    Returns:
        The same error, for the catch site to re-raise.
    """
    table_error.with_input(input_name=input_name)
    has_field_param = "field" in error_code_spec(table_error.resolve_error_code()).param_names
    if input_name is not None and has_field_param and table_error.given_params.get("field") is None:
        table_error.with_params(field=input_name)
    return table_error
