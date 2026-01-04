from pydantic import BaseModel

from pipelex.types import StrEnum


class UriKind(StrEnum):
    """Enumeration of supported URI types."""

    HTTP_URL = "http_url"
    LOCAL_PATH = "local_path"
    PIPELEX_STORAGE = "pipelex_storage"
    BASE64_DATA_URL = "base64_data_url"

    @property
    def desc(self) -> str:
        """Return a human-readable description of this URI kind."""
        match self:
            case UriKind.HTTP_URL:
                return "HTTP URL"
            case UriKind.LOCAL_PATH:
                return "Local path"
            case UriKind.PIPELEX_STORAGE:
                return "Pipelex Storage"
            case UriKind.BASE64_DATA_URL:
                return "Base64 data URL"


class ResolvedUriBase(BaseModel):
    """Base class for all resolved URI types.

    Attributes:
        kind: The type of URI (discriminator field).
        original: The original input string that was resolved.
    """

    kind: UriKind
    original: str


class ResolvedHttpUrl(ResolvedUriBase):
    """Resolved HTTP or HTTPS URL.

    Attributes:
        url: The HTTP/HTTPS URL.
    """

    kind: UriKind = UriKind.HTTP_URL
    url: str


class ResolvedLocalPath(ResolvedUriBase):
    """Resolved local file path.

    This includes:
    - Absolute paths (/home/user/file.txt)
    - Relative paths (dir/file.txt)
    - Simple file names (file.txt)
    - Converted file:// URIs

    Attributes:
        path: The local file path.
    """

    kind: UriKind = UriKind.LOCAL_PATH
    path: str


class ResolvedPipelexStorage(ResolvedUriBase):
    """Resolved pipelex-storage:// URI.

    Attributes:
        storage_uri: The full pipelex-storage:// URI (including scheme).
    """

    kind: UriKind = UriKind.PIPELEX_STORAGE
    storage_uri: str


class ResolvedBase64DataUrl(ResolvedUriBase):
    """Resolved base64 data URL (data:{mime};base64,{data}).

    Attributes:
        mime_type: The MIME type from the data URL (e.g., "image/png").
        base64_data: The base64-encoded data (without the data URL prefix).
    """

    kind: UriKind = UriKind.BASE64_DATA_URL
    mime_type: str
    base64_data: str


# Type alias for the union of all resolved URI types
ResolvedUri = ResolvedHttpUrl | ResolvedLocalPath | ResolvedPipelexStorage | ResolvedBase64DataUrl
