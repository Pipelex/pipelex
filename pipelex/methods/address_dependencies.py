"""Where a library load looks for the method packages its bundles call by their address.

A bundle calls a pipe of another method package by the package's address, such as
`github.com/Pipelex/methods/documents->documents.extract_page_contents_and_views`. A load finds that package among the
packages shipped with the method first (its `methods_dirs`), and, when it may, among the methods installed on this host,
fetching one over the network on a miss. A host resolving a caller's method statically, such as the API server's crate
routes, reads nothing of its own and fetches nothing: a package the caller did not ship is refused, with the refusal
`unshipped_address_dependency_message` words, which a client tells apart by `ADDRESS_DEPENDENCY_REFUSAL_MARKER`.
"""

from enum import StrEnum

#: The words every refusal of an address-based dependency nothing shipped carries, which a client matches to tell that
#: refusal apart from the method being invalid (`pipelex.hosted.hosted_inputs`).
ADDRESS_DEPENDENCY_REFUSAL_MARKER = "address-based dependency"


class AddressDependencySources(StrEnum):
    """Where a load looks for a package its bundles call by address."""

    SHIPPED = "shipped"
    """The packages shipped with the method alone: nothing installed on this host is read, and nothing is fetched."""

    ANYWHERE = "anywhere"
    """The shipped packages first, then the methods installed on this host, then a fetch when fetch-on-miss is enabled."""


def unshipped_address_dependency_message(*, alias: str) -> str:
    """The refusal of an address-based dependency a static resolution cannot load, since nothing shipped it."""
    return (
        f"In-memory resolve cannot load {ADDRESS_DEPENDENCY_REFUSAL_MARKER} '{alias}' from the host filesystem; "
        "provide the dependency contents in the request or use directory-based resolution."
    )
