"""The package's errors, each published under the page and title of its nearest generic family.

A client that receives one of these in an error report reads its RFC 7807 `type` and `title`, so each
class declares both rather than deriving them from its name: the page is the existing public one of
the family the failure belongs to, and the title names the failure, not the component that raised it.
Faults in the operator's configuration, a missing endpoint or credential, keep messages as precise as
the operator needs, since they fail a boot or a worker build and never reach a client.
"""

from pipelex.cogt.exceptions import CogtError
from pipelex.urls import URLs

_COGT_ERROR_PAGE = f"{URLs.error_docs_base}/cogt-error/"
_CREDENTIALS_ERROR_PAGE = f"{URLs.error_docs_base}/inference-backend-credentials-error/"
_EXTRACT_FAILURE_PAGE = f"{URLs.error_docs_base}/extract-job-failure-error/"
_SEARCH_FAILURE_PAGE = f"{URLs.error_docs_base}/search-job-failure-error/"


class ManifoldError(CogtError):
    _declared_type_uri = _COGT_ERROR_PAGE
    _declared_title = "Inference backend error"


class ManifoldFactoryError(ManifoldError):
    _declared_type_uri = _COGT_ERROR_PAGE
    _declared_title = "Inference client setup error"


class ManifoldCredentialsError(ManifoldError):
    _declared_type_uri = _CREDENTIALS_ERROR_PAGE
    _declared_title = "Inference backend credentials missing"


class ManifoldEndpointError(ManifoldError):
    """The backend declares no usable endpoint for the Pipelex Manifold service.

    Its own error rather than a credentials one, because the remedy is a different variable and
    because there is deliberately no default to fall back on: an empty-resolving endpoint that
    silently became a vendor's public URL would carry our service token to the wrong company.
    """

    _declared_type_uri = _CREDENTIALS_ERROR_PAGE
    _declared_title = "Inference backend endpoint missing"


class ManifoldExtractResponseError(ManifoldError):
    _declared_type_uri = _EXTRACT_FAILURE_PAGE
    _declared_title = "Extract response unreadable"


class ManifoldSearchResponseError(ManifoldError):
    _declared_type_uri = _SEARCH_FAILURE_PAGE
    _declared_title = "Search response unreadable"


class ManifoldSearchEmptyResultError(ManifoldError):
    _declared_type_uri = _SEARCH_FAILURE_PAGE
    _declared_title = "Search returned no result"
