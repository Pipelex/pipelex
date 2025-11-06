from importlib.metadata import metadata


def get_package_name() -> str:
    """Get the package name.

    Returns:
        str: The package name.
    """
    return __name__.split(".", maxsplit=1)[0]


def get_package_info() -> tuple[str, str]:
    """Get the package name and version.

    Returns:
        tuple[str, str]: A tuple of (package_name, package_version).
    """
    package_name = get_package_name()
    package_version = metadata(package_name)["Version"]
    return package_name, package_version


def get_package_version() -> str:
    """Get the package version.

    Returns:
        str: The package version.
    """
    _, package_version = get_package_info()
    return package_version
