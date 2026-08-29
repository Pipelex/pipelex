"""Fetch-on-miss for address-based method references.

When a bundle references another method by address (``github.com/...->domain.pipe``) and no
installed method matches, this module bridges the miss: it fetches the package by reference
(honoring ``@<tag>``, through the same grammar, bounds, and tag-only rules as a direct CLI
fetch), installs it into the installed-methods store (``~/.mthds/methods/``) with its fetch
provenance recorded, and hands it back so library loading can proceed. A miss that cannot be
bridged — fetch disabled, an unfetchable address, a failed fetch — raises a diagnostic that
names the address and the remedy; it is never a silent pass.
"""

import shutil
import tempfile
from pathlib import Path

from pipelex import log
from pipelex.cli.installed_methods import InstalledMethod, find_method_by_full_address, install_method_package
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
from pipelex.methods.structures_check import (
    STRUCTURES_REFUSAL_RULE,
    describe_structured_content_violations,
    scan_structured_content_classes,
)

MANUAL_INSTALL_HINT = "install the method manually (e.g. `mthds install <address>`, or copy the package into ~/.mthds/methods/)"


def _warn_on_tag_mismatch(*, installed: InstalledMethod, ref: MethodRef | None) -> None:
    """Warn when a tag-pinned reference resolves to an installed copy that is not that tag."""
    if ref is None or ref.tag is None:
        return
    if installed.provenance is not None and installed.provenance.tag == ref.tag:
        return
    if installed.provenance is None:
        installed_desc = "of unrecorded provenance"
    else:
        installed_desc = f"fetched at tag '{installed.provenance.tag}'" if installed.provenance.tag else "fetched with no tag"
    log.warning(
        f"Method '{ref.address}' is already installed at '{installed.path}' ({installed_desc}) while the reference pins "
        f"'@{ref.tag}'; using the installed copy. Remove '{installed.path}' to re-fetch at the pinned tag."
    )


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
    ref: MethodRef | None = None
    parse_error: MethodRefParseError | None = None
    lookup_address = full_address
    if looks_like_method_ref(full_address):
        try:
            ref = parse_method_ref(full_address)
            lookup_address = ref.address
        except MethodRefParseError as exc:
            parse_error = exc

    installed = find_method_by_full_address(lookup_address, extra_search_dirs=extra_search_dirs)
    if installed is not None:
        _warn_on_tag_mismatch(installed=installed, ref=ref)
        return installed

    if parse_error is not None:
        msg = (
            f"Method '{full_address}' is not installed and its reference cannot be parsed: {parse_error} Fix the reference, or {MANUAL_INSTALL_HINT}."
        )
        raise MethodDependencyFetchError(msg) from parse_error
    if ref is None:
        msg = (
            f"Method '{full_address}' is not installed and cannot be fetched (only github.com/... addresses are fetchable). "
            f"Install it into ~/.mthds/methods/ or .mthds/methods/."
        )
        raise MethodDependencyFetchError(msg)
    if not is_method_fetch_on_miss_enabled():
        msg = (
            f"Method '{ref.ref_str}' is referenced but not installed, and fetch-on-miss is disabled. "
            f"Enable it with `fetch_on_miss = true` under [interpreter.methods] in your pipelex.toml "
            f"(or {METHODS_FETCH_ON_MISS_ENV_VAR}=1), or {MANUAL_INSTALL_HINT}."
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
                f"Method '{ref.ref_str}' is not installed and fetching it failed: {exc} "
                f"Check the address, tag, and network access, or {MANUAL_INSTALL_HINT}."
            )
            raise MethodDependencyFetchError(msg) from exc

        violations = scan_structured_content_classes(package_dir=fetched.package_dir)
        if violations:
            details = describe_structured_content_violations(violations=violations)
            log.warning(
                f"Method '{fetched.full_address}' declares Python structure classes ({details}). It runs locally, but "
                f"{STRUCTURES_REFUSAL_RULE} — hosted execution would refuse it. Express the types as MTHDS concepts "
                f"to keep the method hosted-runnable."
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

    log.info(f"Fetched method '{fetched.full_address}' at commit {fetched.commit_sha} and installed it into '{installed.path}'")
    return installed
