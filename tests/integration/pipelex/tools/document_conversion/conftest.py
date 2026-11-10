import os
import shutil
from pathlib import Path

import pytest

from pipelex.tools.document_conversion.document_converter_protocol import DocumentConverterProtocol
from pipelex.tools.document_conversion.gotenberg_converter import GotenbergConverter
from pipelex.tools.document_conversion.soffice_converter import SofficeConverter
from tests.integration.pipelex.tools.document_conversion.test_data import DocumentConversionTestData

_MAX_SOURCE_BYTES = 50_000_000


@pytest.fixture(params=["soffice", "gotenberg"])
def document_converter(request: pytest.FixtureRequest) -> DocumentConverterProtocol:
    """Each backend this machine has, the test skipped for one it lacks.

    `soffice` is the executable `PIPELEX_TEST_SOFFICE_BINARY` names, else `soffice` on the PATH; Gotenberg is the container
    at `PIPELEX_TEST_GOTENBERG_URL`, such as one started with `docker run --rm -p 3000:3000 gotenberg/gotenberg:8`.
    """
    match request.param:
        case "soffice":
            binary = os.environ.get(DocumentConversionTestData.SOFFICE_BINARY_ENV_VAR) or DocumentConversionTestData.DEFAULT_SOFFICE_BINARY
            found_binary = shutil.which(binary)
            if found_binary is None:
                pytest.skip(f"soffice not found: install LibreOffice or set {DocumentConversionTestData.SOFFICE_BINARY_ENV_VAR}")
            return SofficeConverter(binary_path=Path(found_binary), timeout_seconds=120, max_source_bytes=_MAX_SOURCE_BYTES)
        case _:
            gotenberg_url = os.environ.get(DocumentConversionTestData.GOTENBERG_URL_ENV_VAR)
            if not gotenberg_url:
                pytest.skip(f"no Gotenberg container: set {DocumentConversionTestData.GOTENBERG_URL_ENV_VAR}")
            return GotenbergConverter(
                base_url=gotenberg_url,
                configured_version=None,
                timeout_seconds=360,
                budget_seconds=120,
                max_source_bytes=_MAX_SOURCE_BYTES,
            )
