"""The view of a problem a request's reader sees, picked by the identity the request authenticated.

A failure answered to a request is one problem document seen through a view, and who made the request decides which
(`pipelex.errors.problem`): the operator, whoever runs this runner, reads the operator view, with `diagnostics` and the
operator's step; anyone else reads the caller view. No deployment setting picks it.

The authentication dependencies in `pipelex_api.security` mark a request as the operator's when the identity they
authenticated is the operator's:

- `AUTH_MODE=api_key`: the static API key is the operator's own credential, so whoever presents it is the operator, as a
  developer running this server locally is.
- `AUTH_MODE=none` with `TRUST_FORWARDED_IDENTITY_HEADERS=true`: the only party that reaches this server is the trusted
  proxy in front of it, such as the hosted platform, which is the deployment's own hop and reads the operator view. It
  owes its own callers their caller view.

A request authenticated by a caller's token (`AUTH_MODE=jwt`), a request to a server with no authentication and no
trusted proxy, and a request refused before any authentication ran are a caller's, and read the caller view: the view
falls back to the caller's whenever nothing marked the request.
"""

from pipelex.errors.problem import ProblemView
from starlette.requests import Request


def mark_operator_request(request: Request) -> None:
    """Record that the request was authenticated as the operator's, so its failures answer the operator view."""
    request.state.problem_view = ProblemView.OPERATOR


def problem_view_of(request: Request) -> ProblemView:
    """The view of a problem the request's reader sees: the operator's when authentication marked it so, else the caller's."""
    view = getattr(request.state, "problem_view", None)
    if isinstance(view, ProblemView):
        return view
    return ProblemView.CALLER
