from typing import ClassVar

from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind


class HostedRunError(PipelexError):
    """Base class for errors pipelex raises itself while running a method on the hosted Pipelex API.

    An error the hosted API answers, or one the pipelex-sdk client raises on the way, keeps the SDK's own class
    (`ApiResponseError`, `ApiUnreachableError`, `RunFailedError`, …); these are the ones pipelex detects before it
    sends anything.
    """

    _declared_title = "Hosted run error"


class HostedBaseUrlError(HostedRunError):
    """The base URL of the hosted API is not an origin: it carries a path, a query, credentials, or a scheme other than http or https.

    The message names where the value came from, `--base-url` or `PIPELEX_BASE_URL`, and what an origin looks like.
    """

    error_domain = ErrorDomain.INPUT
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Give the hosted API's origin as scheme://host[:port], such as https://api.pipelex.com, in --base-url or PIPELEX_BASE_URL",
    )
    _authors_caller_facing_message: ClassVar[bool] = True


class HostedRunSourceError(HostedRunError):
    """A hosted run cannot be given the method to run: no bundle file, no `.mthds` file in the library directories, or no source at all."""

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message: ClassVar[bool] = True
