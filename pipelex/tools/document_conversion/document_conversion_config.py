from enum import StrEnum
from typing import Annotated

from pydantic import Field

from pipelex.system.configuration.config_model import ConfigModel


class DocumentConversionBackend(StrEnum):
    """Which converter makes the PDF of an Office file a step reads, or `none` for no conversion at all."""

    NONE = "none"
    GOTENBERG = "gotenberg"
    SOFFICE = "soffice"


class GotenbergConversionConfig(ConfigModel):
    """`[runtime.document_conversion.gotenberg]`: a Gotenberg container reached over HTTP."""

    # The container's base URL, such as `http://localhost:3000`. Empty is unset, which a boot naming this backend refuses.
    url: str
    # The version stamped on the PDFs this backend makes. Empty asks Gotenberg's `GET /version` once; the hosted worker
    # sets its converter image's own version, as the platform's preview worker stamps it.
    version: str
    # How long the client waits for Gotenberg's answer. A hostile file can hold a connection about six minutes before
    # Gotenberg's hard timeout closes it, so this allows for more.
    timeout_seconds: Annotated[float, Field(gt=0)]
    # Gotenberg's own budget for one conversion, queue included: its `--api-timeout`. A connection that ends with no
    # answer after it is the file outrunning its budget; before it, the converter going away.
    budget_seconds: Annotated[float, Field(gt=0)]


class SofficeConversionConfig(ConfigModel):
    """`[runtime.document_conversion.soffice]`: LibreOffice's `soffice` run on this machine."""

    # The executable, a name looked up on the PATH or a path to it.
    binary: str
    # How long one conversion may run before its process group is killed.
    timeout_seconds: Annotated[float, Field(gt=0)]


class DocumentConversionConfig(ConfigModel):
    """`[runtime.document_conversion]`: whether, and with what, the runtime converts an Office file to a PDF.

    Off by default, `none`, and then every check and every step behaves as if no conversion existed. A backend named
    but unusable fails the boot with `runtime.misconfigured` rather than the first Office file.
    """

    backend: DocumentConversionBackend = Field(strict=False)
    # The largest source the runtime hands a converter, the platform converter's own input cap.
    max_source_bytes: Annotated[int, Field(ge=1)]
    gotenberg: GotenbergConversionConfig
    soffice: SofficeConversionConfig
