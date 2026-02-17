from typing import Any, cast

import tomlkit
from pydantic import ValidationError

from pipelex.core.packages.exceptions import ManifestParseError, ManifestValidationError
from pipelex.core.packages.manifest import DomainExports, MthdsPackageManifest, PackageDependency
from pipelex.tools.misc.toml_utils import TomlError, load_toml_from_content


def _walk_exports_table(table: dict[str, Any], prefix: str = "") -> list[DomainExports]:
    """Recursively walk nested exports sub-tables to reconstruct dotted domain paths.

    Given a TOML structure like:
        [exports.legal.contracts]
        pipes = ["extract_clause"]

    This produces DomainExports(domain_path="legal.contracts", pipes=["extract_clause"]).

    Args:
        table: The current dict-level of the exports table
        prefix: The dotted path prefix accumulated so far

    Returns:
        List of DomainExports built from nested sub-tables
    """
    result: list[DomainExports] = []

    for key, value in table.items():
        current_path = f"{prefix}.{key}" if prefix else str(key)

        if isinstance(value, dict):
            value_dict = cast("dict[str, Any]", value)
            # Check if this level has a "pipes" key (leaf domain)
            if "pipes" in value_dict:
                pipes_value = value_dict["pipes"]
                if not isinstance(pipes_value, list):
                    msg = f"'pipes' in domain '{current_path}' must be a list, got {type(pipes_value).__name__}"
                    raise ManifestValidationError(msg)
                pipes_list = cast("list[str]", pipes_value)
                result.append(DomainExports(domain_path=current_path, pipes=pipes_list))

                # Also recurse into remaining sub-tables (a domain can have both pipes and sub-domains)
                for sub_key, sub_value in value_dict.items():
                    if sub_key != "pipes" and isinstance(sub_value, dict):
                        sub_dict = cast("dict[str, Any]", {sub_key: sub_value})
                        result.extend(_walk_exports_table(sub_dict, prefix=current_path))
            else:
                # No pipes at this level, just recurse deeper
                result.extend(_walk_exports_table(value_dict, prefix=current_path))

    return result


def parse_methods_toml(content: str) -> MthdsPackageManifest:
    """Parse METHODS.toml content into an MthdsPackageManifest model.

    Args:
        content: The raw TOML string

    Returns:
        A validated MthdsPackageManifest

    Raises:
        ManifestParseError: If the TOML syntax is invalid
        ManifestValidationError: If the parsed data fails model validation
    """
    try:
        raw = load_toml_from_content(content)
    except TomlError as exc:
        msg = f"Invalid TOML syntax in METHODS.toml: {exc.message}"
        raise ManifestParseError(msg) from exc

    # Extract [package] section
    package_section = raw.get("package")
    if not isinstance(package_section, dict):
        msg = "METHODS.toml must contain a [package] section"
        raise ManifestValidationError(msg)
    pkg = cast("dict[str, Any]", package_section)

    # Extract [dependencies] section
    deps_section = raw.get("dependencies", {})
    dependencies: list[PackageDependency] = []
    if isinstance(deps_section, dict):
        deps_dict = cast("dict[str, Any]", deps_section)
        for alias, dep_data in deps_dict.items():
            if isinstance(dep_data, dict):
                dep_data_dict = cast("dict[str, Any]", dep_data)
                dep_data_dict["alias"] = str(alias)
                try:
                    dependencies.append(PackageDependency(**dep_data_dict))
                except ValidationError as exc:
                    msg = f"Invalid dependency '{alias}' in METHODS.toml: {exc}"
                    raise ManifestValidationError(msg) from exc
            else:
                msg = (
                    f"Invalid dependency '{alias}' in METHODS.toml: expected a table with 'address' and 'version' keys, got {type(dep_data).__name__}"
                )
                raise ManifestValidationError(msg)

    # Extract [exports] section with recursive walk
    exports_section = raw.get("exports", {})
    exports: list[DomainExports] = []
    if isinstance(exports_section, dict):
        exports_dict = cast("dict[str, Any]", exports_section)
        try:
            exports = _walk_exports_table(exports_dict)
        except ValidationError as exc:
            msg = f"Invalid exports in METHODS.toml: {exc}"
            raise ManifestValidationError(msg) from exc

    # Build the manifest
    address: str = str(pkg.get("address", ""))
    version: str = str(pkg.get("version", ""))
    description: str = str(pkg.get("description", ""))
    authors_val = pkg.get("authors", [])
    authors: list[str] = cast("list[str]", authors_val) if isinstance(authors_val, list) else []
    license_val = pkg.get("license")
    license_str: str | None = str(license_val) if license_val is not None else None
    mthds_version_val = pkg.get("mthds_version")
    mthds_version: str | None = str(mthds_version_val) if mthds_version_val is not None else None

    try:
        manifest = MthdsPackageManifest(
            address=address,
            version=version,
            description=description,
            authors=authors,
            license=license_str,
            mthds_version=mthds_version,
            dependencies=dependencies,
            exports=exports,
        )
    except ValidationError as exc:
        msg = f"METHODS.toml validation failed: {exc}"
        raise ManifestValidationError(msg) from exc

    return manifest


def serialize_manifest_to_toml(manifest: MthdsPackageManifest) -> str:
    """Serialize an MthdsPackageManifest to a human-readable TOML string.

    Args:
        manifest: The manifest model to serialize

    Returns:
        A TOML-formatted string
    """
    doc = tomlkit.document()

    # [package] section
    package_table = tomlkit.table()
    package_table.add("address", manifest.address)
    package_table.add("version", manifest.version)
    package_table.add("description", manifest.description)
    if manifest.authors:
        package_table.add("authors", manifest.authors)
    if manifest.license is not None:
        package_table.add("license", manifest.license)
    if manifest.mthds_version is not None:
        package_table.add("mthds_version", manifest.mthds_version)
    doc.add("package", package_table)

    # [dependencies] section
    if manifest.dependencies:
        doc.add(tomlkit.nl())
        deps_table = tomlkit.table()
        for dep in manifest.dependencies:
            dep_table = tomlkit.inline_table()
            dep_table.append("address", dep.address)
            dep_table.append("version", dep.version)
            if dep.path is not None:
                dep_table.append("path", dep.path)
            deps_table.add(dep.alias, dep_table)
        doc.add("dependencies", deps_table)

    # [exports] section — build nested tables from dotted domain paths
    if manifest.exports:
        doc.add(tomlkit.nl())
        exports_table = tomlkit.table(is_super_table=True)

        for domain_export in manifest.exports:
            segments = domain_export.domain_path.split(".")
            # Navigate/create nested tables
            current: Any = exports_table
            for segment in segments:
                if segment not in current:
                    current.add(segment, tomlkit.table())
                current = current[segment]
            current.add("pipes", domain_export.pipes)

        doc.add("exports", exports_table)

    return tomlkit.dumps(doc)  # type: ignore[arg-type]
