"""Reading the file a run supplies as a `PipeDocGen` step's template, where IO is allowed.

A step with `template_input` takes its office template from one of its inputs rather than from its method tree. The
compose stage names the input's document by its URL (`TemplateInputFile`), and the file is read here, by the print
stage, an activity on a hosted plane, and by run setup, which hands it to the engine's template checker before any step
starts. Either reads it as it reads any file the run names, under the run's read scope: a storage URI through the
storage provider, an `https://` URL through the guarded fetch, capped by `[runtime.network] max_fetch_bytes`. A file
that is not of the step's format is refused, naming the input, before an engine sees it.
"""

from pipelex.cogt.content_generation.read_authorization import authorize_method_uri_read
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat
from pipelex.cogt.doc_gen.document_composition import TemplateInputFile
from pipelex.cogt.doc_gen.exceptions import DocGenTemplateInputFormatError
from pipelex.cogt.doc_gen.template_input_format import judge_file_format
from pipelex.tools.misc.filetype_utils import UNKNOWN_FILE_TYPE, describe_file_format, describe_format_key
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.uri_bytes import load_bytes_and_mime_type_from_any_uri


def template_input_position(*, input_file: TemplateInputFile, pipe_code: str | None) -> str:
    """Where the template input's URL sits, in words, for a refusal of its read: "the template the input 'workbook' supplies"."""
    position = f"the template the input '{input_file.input_name}' supplies"
    return f"{position} to pipe '{pipe_code}'" if pipe_code else position


async def read_template_input(
    *,
    input_file: TemplateInputFile,
    doc_gen_format: DocGenFormat,
    pipe_code: str | None,
    engine: str,
    read_scope: str | None,
    storage_provider: StorageProviderAbstract,
) -> bytes:
    """Read the file a run input supplies as the step's template, refusing one that is not of the step's format.

    Args:
        input_file: The input's document, as the compose stage named it.
        doc_gen_format: The step's format, which the file must be.
        pipe_code: The step, for the messages.
        engine: The engine that fills the template, which a format refusal names as its model.
        read_scope: The run's read scope.
        storage_provider: The run's storage provider, which resolves a storage URI.

    Returns:
        The file's bytes.

    Raises:
        UriReadRefusedError: the run's read scope does not allow the document's URL.
        DocGenTemplateInputFormatError: the file is not of the step's format.
        StorageFileNotFoundError: the storage provider holds nothing under the document's URI.
        RemoteFileFetchError: the document's https URL could not be fetched.
        RemoteFileTooLargeError: the document's https URL serves more than the fetch cap.
        SsrfBlockedError: the document's https URL, or a redirect hop, is a private or metadata address.
    """
    authorize_method_uri_read(uri=input_file.url, read_scope=read_scope, position=template_input_position(input_file=input_file, pipe_code=pipe_code))
    loaded = await load_bytes_and_mime_type_from_any_uri(input_file.url, storage_provider=storage_provider)
    check_template_input_format(
        data=loaded.data,
        mime_type=input_file.mime_type or loaded.mime_type,
        input_file=input_file,
        doc_gen_format=doc_gen_format,
        pipe_code=pipe_code,
        engine=engine,
    )
    return loaded.data


def check_template_input_format(
    *,
    data: bytes,
    mime_type: str | None,
    input_file: TemplateInputFile,
    doc_gen_format: DocGenFormat,
    pipe_code: str | None,
    engine: str,
) -> None:
    """Refuse a template input whose file is not of the step's format, judged from its bytes, its media type, then its name.

    Raises:
        DocGenTemplateInputFormatError: the file is judged another format, or nothing tells its format.
    """
    file_format = judge_file_format(data=data, mime_type=mime_type, file_name=input_file.filename)
    expected_format = doc_gen_format.suffix
    if file_format == expected_format:
        return
    file_desc = describe_file_format(format_key=file_format, mime_type=mime_type) if file_format is not None else "a file of no known format"
    step_label = f"PipeDocGen '{pipe_code}'" if pipe_code else "The PipeDocGen step"
    expected_desc = describe_file_format(format_key=expected_format, mime_type=None)
    msg = (
        f"The input '{input_file.input_name}' is {file_desc}, and {step_label} fills it as its template, "
        f"which must be {expected_desc}. Give the input {describe_format_key(format_key=expected_format)}."
    )
    raise DocGenTemplateInputFormatError(msg, input_name=input_file.input_name, file_format=file_format or UNKNOWN_FILE_TYPE, model=engine)
