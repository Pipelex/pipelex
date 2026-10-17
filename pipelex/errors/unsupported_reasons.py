"""The reasons the runtime gives `request.unsupported` that a client tells one refusal apart by.

A reason rides the problem's `params.reason`, so a client branches on the code and the reason together, never on
the problem's text. This module imports nothing, so a client of the hosted API reads it without loading the
interpreter.
"""

#: Contents-only resolution, the core of `POST /v1/pipe-io`, met a method calling another one by its address, which it
#: cannot fetch. A hosted run tells this refusal apart by it, since the run route fetches such a dependency.
ADDRESS_DEPENDENCY_UNSUPPORTED_REASON = "address_based_dependency"
