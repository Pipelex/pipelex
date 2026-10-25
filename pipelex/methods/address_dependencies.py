"""Where a library load looks for the method packages its bundles call by their address.

A bundle calls a pipe of another method package by the package's address, such as
`github.com/Pipelex/methods/documents->documents.extract_page_contents_and_views`. A load finds that package among the
packages shipped with the method first (its `methods_dirs`), and, when it may, among the methods installed on this host,
fetching one over the network on a miss. A host resolving a caller's method statically, such as the API server's crate
routes, reads nothing of its own and fetches nothing: a package the caller did not ship is refused, with the refusal
`unshipped_address_dependency_message` words for the operator, and as a `method.dependency_missing` item of the kind
`package` naming its address, by which a client tells that refusal apart (`pipelex.hosted.hosted_inputs`).
"""

from enum import StrEnum


class AddressDependencySources(StrEnum):
    """Where a load looks for a package its bundles call by address."""

    SHIPPED = "shipped"
    """The packages shipped with the method alone: nothing installed on this host is read, and nothing is fetched."""

    ANYWHERE = "anywhere"
    """The shipped packages first, then the methods installed on this host, then a fetch when fetch-on-miss is enabled."""


def unshipped_address_dependency_message(*, alias: str) -> str:
    """The refusal of an address-based dependency a static resolution cannot load, since nothing shipped it.

    The advice is what the caller of such a resolution can do, such as the caller of the API server's `/v1/resolve`,
    `/v1/codegen` and `/v1/pipe-io`: send the package's files in the request's `dependencies`, keyed by its address,
    beside the method's own in `files`.
    """
    return (
        f"The method calls the address-based dependency '{alias}', which was not sent with it, and this "
        "resolution loads only the packages sent with the method, fetching none: send the package's files in "
        "`dependencies`, keyed by its address, beside the method's own files in `files`."
    )
