"""The reasons a method's package breaks a package rule, the `reason` of `method.package_invalid`."""

from enum import StrEnum, unique


@unique
class MethodPackageReason(StrEnum):
    """The `reason` of a `method.package_invalid` the runtime and its runner raise themselves, one member per rule and one per limit.

    Beside them, a refusal of the standard's tree rule gives the standard's own refusal code (`TreeRefusalCode`) as its
    reason. A limit's refusal also gives its `limit`, and each limit has its own reason, so a caller reads which one the
    method passed: a tree's, a request's, a `bundle_b64` archive's or a fetched package's `.mthds` file's.
    """

    # The limits of one method tree.
    TOO_MANY_FILES = "too_many_files"
    FILE_TOO_LARGE = "file_too_large"
    TREE_TOO_LARGE = "tree_too_large"
    # The limits of a request's trees together.
    TOO_MANY_DEPENDENCIES = "too_many_dependencies"
    METHOD_TOO_LARGE = "method_too_large"
    # The limits of a `bundle_b64` archive, on its members and on its decompressed size.
    BUNDLE_TOO_MANY_FILES = "bundle_too_many_files"
    BUNDLE_TOO_LARGE = "bundle_too_large"
    # The limit on one `.mthds` file of a package fetched by `method_ref` for a tooling route.
    MTHDS_FILE_TOO_LARGE = "mthds_file_too_large"
    # The method's own tree holds no `.mthds` bundle.
    NO_BUNDLE = "no_bundle"
    # The manifest of a shipped package or of a dependency tree.
    MANIFEST_MISSING = "manifest_missing"
    MANIFEST_INVALID = "manifest_invalid"
    PACKAGE_NAME_INVALID = "package_name_invalid"
    # Two dependencies a reference could not tell apart.
    DEPENDENCY_ADDRESS_COLLISION = "dependency_address_collision"
    # A fetched package holds a file whose name is not UTF-8 text.
    FILE_NAME_NOT_UTF8 = "file_name_not_utf8"
    # A fetched package holds a symbolic link, which would let a file reach outside it past the content scans.
    SYMLINK = "symlink"
    # A fetched repository holds more manifests than the runtime scans for the package an address names.
    TOO_MANY_MANIFESTS = "too_many_manifests"
    # The method's `requirements.txt` holds a line the standard refuses, or cannot be read as UTF-8 text.
    REQUIREMENTS_INVALID = "requirements_invalid"
    # A version, or a version constraint, the package declares does not parse.
    VERSION_INVALID = "version_invalid"
    # The method's tree cannot be listed: a path it names is missing, one of its files cannot be read, or its manifest does not parse.
    TREE_UNREADABLE = "tree_unreadable"
