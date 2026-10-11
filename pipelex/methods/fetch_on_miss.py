"""Fetch-on-miss for address-based method references.

When a bundle references another method by address (``github.com/...->domain.pipe``) and no
installed method matches, this module bridges the miss: it fetches the package by reference
(honoring ``@<tag>``, through the same grammar, bounds, and tag-only rules as a direct CLI
fetch), installs it into the installed-methods store (``~/.mthds/methods/``) with its fetch
provenance recorded, and hands it back so library loading can proceed. A miss that cannot be
bridged — fetch disabled, an unfetchable address, a failed fetch — raises a diagnostic that
names the address and the remedy; it is never a silent pass.

A load can also be handed methods directories of its own, holding the packages a request ships
with its bundle under `.mthds/methods/<name>/`. They are looked up first, by the same manifest
identity, and only searched, never written (:func:`find_vendored_method`).
"""

import shutil
import tempfile
from pathlib import Path
from typing import NamedTuple

from pipelex import log
from pipelex.cli.installed_methods import InstalledMethod, discover_installed_methods, find_method_by_full_address, install_method_package
from pipelex.config import METHODS_FETCH_ON_MISS_ENV_VAR, is_method_fetch_on_miss_enabled, is_pipe_func_sandbox_hosted
from pipelex.methods.exceptions import (
    MethodDependencyFetchError,
    MethodFetchDisabledError,
    MethodRefError,
    MethodRefParseError,
    MethodStructuresRefusedError,
)
from pipelex.methods.fetching import fetch_method_package
from pipelex.methods.method_ref import MethodRef, looks_like_method_ref, parse_method_ref
from pipelex.methods.structures_check import describe_structured_content_violations, scan_structured_content_classes
from pipelex.system.telemetry.otel_constants import OTelLogAttr
from pipelex.tools.log.log_fields import USER_ACTION_FIELD

# The remedy every refusal ends with. It names no directory: on a host, the runtime's own store is not the caller's to write.
MANUAL_INSTALL_HINT = "install the package where this runtime runs (for example with `mthds install <address>`)"

# The remedy a caller can always apply, a hosted one included: the bundle carries the package, which the runtime then
# finds before its own store, beside a bundle on disk as in a bundle sent over HTTP.
VENDORING_HINT = "ship the package with the bundle under `.mthds/methods/<name>/`"


class _LookupAddress(NamedTuple):
    """The address a reference is looked up by, with the parsed reference or the reason it did not parse."""

    address: str
    ref: MethodRef | None
    parse_error: MethodRefParseError | None


def _lookup_address(*, full_address: str) -> _LookupAddress:
    """Strip any ``@<tag>`` from a reference for the lookup: an installed or vendored copy is keyed by its address alone."""
    if not looks_like_method_ref(full_address):
        return _LookupAddress(address=full_address, ref=None, parse_error=None)
    try:
        ref = parse_method_ref(full_address)
    except MethodRefParseError as exc:
        return _LookupAddress(address=full_address, ref=None, parse_error=exc)
    return _LookupAddress(address=ref.address, ref=ref, parse_error=None)


def find_vendored_method(*, full_address: str, methods_dirs: list[Path]) -> InstalledMethod | None:
    """Look an address-based reference up among the packages a load was handed, and nowhere else.

    ``methods_dirs`` are laid out like ``.mthds/methods/`` (one directory per package, its ``METHODS.toml`` at its
    root) and hold the packages a request ships with its bundle. A package matches by the manifest identity the
    installed stores are matched by, any ``@<tag>`` stripped, so a vendored copy answers an address this runtime could
    not fetch too. The installed stores are not read, and nothing is fetched or installed. A ``@<tag>`` pin answered by
    a vendored copy uses the copy, as an installed copy is used, with a warning unless the copy's version is that tag.

    Args:
        full_address: The address-based alias as written in the bundle, with any ``@<tag>``.
        methods_dirs: The load's own methods directories.

    Returns:
        The vendored package the reference names, or ``None`` when none of the directories holds it.
    """
    lookup = _lookup_address(full_address=full_address)
    vendored_methods = discover_installed_methods(include_global=False, include_project=False, extra_search_dirs=methods_dirs)
    vendored = find_method_by_full_address(lookup.address, methods=vendored_methods)
    if vendored is not None and lookup.ref is not None and lookup.ref.tag is not None:
        version = vendored.manifest.version
        if lookup.ref.tag not in {version, f"v{version}"}:
            log.warning(
                "A shipped method copy was used though its version is not the pinned tag",
                fields={"method_ref": lookup.ref.ref_str, "package_version": version},
            )
    return vendored


def _warn_on_tag_mismatch(*, installed: InstalledMethod, ref: MethodRef | None) -> None:
    """Warn when a tag-pinned reference resolves to an installed copy that is not that tag."""
    if ref is None or ref.tag is None:
        return
    if installed.provenance is not None and installed.provenance.tag == ref.tag:
        return
    mismatch_fields: dict[str, str | None] = {
        "method_ref": ref.ref_str,
        OTelLogAttr.FILE_PATH: str(installed.path),
        USER_ACTION_FIELD: "Remove the installed copy to fetch the pinned tag",
    }
    if installed.provenance is not None:
        # Absent when the copy's provenance was never recorded, and None when the copy was fetched with no tag.
        mismatch_fields["installed_tag"] = installed.provenance.tag
    log.warning("A method's installed copy was used though not fetched at the pinned tag", fields=mismatch_fields)


def resolve_address_based_method(
    *,
    full_address: str,
    extra_search_dirs: list[Path] | None = None,
    methods_dir: Path | None = None,
) -> InstalledMethod:
    """Resolve an address-based method reference to an installed method, fetching on a miss.

    Looks the address up among installed methods first (with any ``@<tag>`` stripped for the
    lookup — the installed store is keyed by address alone). On a miss, when fetch-on-miss is
    enabled and the address is fetchable, fetches the package by reference and installs it
    into the installed-methods store, recording the fetch provenance (address, tag, commit
    SHA) beside the manifest.

    Args:
        full_address: The address-based alias as written in the bundle, e.g.
            ``github.com/Pipelex/methods/documents`` or ``...documents@v0.1.0``.
        extra_search_dirs: Additional ``.mthds/methods/`` directories to scan for the lookup.
        methods_dir: Override for the installed-methods root the fetch installs into
            (defaults to the global ``~/.mthds/methods/``).

    Returns:
        The installed method the reference resolves to.

    Raises:
        MethodFetchDisabledError: The method is not installed and fetch-on-miss is disabled.
        MethodDependencyFetchError: The method is not installed and its address cannot be
            parsed or fetched, or the fetch failed.
        MethodStructuresRefusedError: On a sandbox-hosted deployment, the fetched package
            declares in-process Python structure classes (locally this is a warning instead).
        MethodInstallError: The fetch succeeded but installing the package failed — including
            the install target being occupied by a different package that shares the bare
            directory name (never silently loaded, never silently overwritten).
    """
    lookup = _lookup_address(full_address=full_address)
    ref = lookup.ref
    parse_error = lookup.parse_error

    installed = find_method_by_full_address(lookup.address, extra_search_dirs=extra_search_dirs)
    if installed is not None:
        _warn_on_tag_mismatch(installed=installed, ref=ref)
        return installed

    if parse_error is not None:
        msg = (
            f"Method '{full_address}' is referenced but not installed, and its address cannot be parsed: {parse_error} "
            f"Correct the address, or {MANUAL_INSTALL_HINT}."
        )
        raise MethodDependencyFetchError(msg) from parse_error
    if ref is None:
        msg = (
            f"Method '{full_address}' is referenced but not installed, and this runtime cannot fetch it: only github.com/... addresses "
            f"are fetchable. Correct the address, {VENDORING_HINT}, or {MANUAL_INSTALL_HINT}."
        )
        raise MethodDependencyFetchError(msg)
    if not is_method_fetch_on_miss_enabled():
        msg = (
            f"Method '{ref.ref_str}' is referenced but not installed, and fetch-on-miss is disabled on this runtime, so it does not "
            f"fetch it. Correct the address if it is wrong, {VENDORING_HINT}, or {MANUAL_INSTALL_HINT}. Fetch-on-miss is enabled by "
            f"`fetch_on_miss = true` under [interpreter.methods] in the runtime's pipelex.toml, or {METHODS_FETCH_ON_MISS_ENV_VAR}=1."
        )
        raise MethodFetchDisabledError(msg)

    clone_dir = Path(tempfile.mkdtemp(prefix="mthds_fetch_on_miss_"))
    try:
        try:
            # Sandbox-hosted deployments hard-refuse fetched packages that declare in-process
            # Python structure classes (the security seam); locally the scan below warns instead.
            fetched = fetch_method_package(ref=ref, dest_dir=clone_dir, refuse_structures=is_pipe_func_sandbox_hosted())
        except MethodStructuresRefusedError:
            # Already the rule-naming refusal — surface it as-is, not as a generic fetch failure.
            raise
        except MethodRefError as exc:
            msg = (
                f"Method '{ref.ref_str}' is referenced but not installed, and fetching it failed: {exc} "
                f"Correct the address or the tag, {VENDORING_HINT}, or {MANUAL_INSTALL_HINT}."
            )
            raise MethodDependencyFetchError(msg) from exc

        violations = scan_structured_content_classes(package_dir=fetched.package_dir)
        if violations:
            # The remedy rides in `user_action`, which the console prints whole; `STRUCTURES_REFUSAL_REMEDY` says it at length in the refusal.
            log.warning(
                "A fetched method declares Python structure classes, which hosted runs refuse",
                fields={
                    "package_address": fetched.full_address,
                    "structure_classes": describe_structured_content_violations(violations=violations),
                    USER_ACTION_FIELD: "Declare these types as MTHDS concepts with inline structures",
                },
            )

        name = fetched.manifest.name or fetched.package_dir.name
        # An occupied install target is resolved by identity inside install_method_package: a
        # concurrent install of the same package (by full address) is returned and used, while a
        # different occupant — two packages sharing the bare name — is a loud collision error.
        installed = install_method_package(
            package_dir=fetched.package_dir,
            name=name,
            full_address=fetched.full_address,
            provenance=fetched.provenance,
            methods_dir=methods_dir,
        )
    finally:
        shutil.rmtree(clone_dir, ignore_errors=True)

    log.info(
        "Fetched a method package and installed it",
        fields={"package_address": fetched.full_address, "commit_sha": fetched.commit_sha, OTelLogAttr.FILE_PATH: str(installed.path)},
    )
    return installed
