import shutil
from pathlib import Path
from urllib.parse import urlsplit

from pipelex.tools.document_conversion.document_conversion_config import DocumentConversionBackend, DocumentConversionConfig
from pipelex.tools.document_conversion.document_converter_protocol import DocumentConverterProtocol
from pipelex.tools.document_conversion.exceptions import DocumentConverterMisconfiguredError
from pipelex.tools.document_conversion.gotenberg_converter import GotenbergConverter
from pipelex.tools.document_conversion.soffice_converter import SofficeConverter


def make_optional_document_converter_from_config(*, config: DocumentConversionConfig) -> DocumentConverterProtocol | None:
    """The converter `[runtime.document_conversion]` names, or None when it names `none`.

    Called at boot, so a backend named but unusable fails the boot rather than the first Office file. Nothing is
    contacted here: a Gotenberg container down at boot is the converter being unavailable later, not a misconfiguration.

    Raises:
        DocumentConverterMisconfiguredError: The Gotenberg backend's URL is not an absolute `http` or `https` URL with
            a host, or the `soffice` binary is not found.
    """
    match config.backend:
        case DocumentConversionBackend.NONE:
            return None
        case DocumentConversionBackend.GOTENBERG:
            gotenberg_config = config.gotenberg
            gotenberg_url = gotenberg_config.url.strip()
            if not gotenberg_url:
                msg = "The document converter is Gotenberg but [runtime.document_conversion.gotenberg] sets no url."
                raise DocumentConverterMisconfiguredError(msg)
            if not _is_absolute_http_url(url=gotenberg_url):
                msg = (
                    f"The document converter is Gotenberg but the url '{gotenberg_url}' set in [runtime.document_conversion.gotenberg] "
                    "is not an absolute http or https URL with a host, such as 'http://localhost:3000'."
                )
                raise DocumentConverterMisconfiguredError(msg)
            return GotenbergConverter(
                base_url=gotenberg_url,
                timeout_seconds=gotenberg_config.timeout_seconds,
                budget_seconds=gotenberg_config.budget_seconds,
                max_source_bytes=config.max_source_bytes,
            )
        case DocumentConversionBackend.SOFFICE:
            soffice_config = config.soffice
            found_binary = shutil.which(soffice_config.binary) if soffice_config.binary.strip() else None
            if found_binary is None:
                msg = (
                    f"The document converter is soffice but the binary '{soffice_config.binary}' set in "
                    "[runtime.document_conversion.soffice] is not found: install LibreOffice or set the binary's path."
                )
                raise DocumentConverterMisconfiguredError(msg)
            return SofficeConverter(
                # Absolute, so a relative path set in the configuration names the same executable from any working directory.
                binary_path=Path(found_binary).resolve(),
                timeout_seconds=soffice_config.timeout_seconds,
                max_source_bytes=config.max_source_bytes,
            )


def _is_absolute_http_url(*, url: str) -> bool:
    """Whether `url` is an absolute `http` or `https` URL naming a host: `localhost:3000` reads as a scheme, not a host."""
    try:
        split_url = urlsplit(url)
        # Reading the port checks it is a number in range.
        _ = split_url.port
    except ValueError:
        return False
    return split_url.scheme in {"http", "https"} and bool(split_url.hostname)
