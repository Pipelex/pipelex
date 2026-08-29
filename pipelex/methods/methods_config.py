from pipelex.system.configuration.config_model import ConfigModel


class MethodsConfig(ConfigModel):
    """Behavior of installed and fetched method packages.

    ``fetch_on_miss``: when a bundle references another method by address
    (``github.com/...->domain.pipe``) and no installed method matches, fetch the package by
    address and install it into the global methods directory so the load can proceed. When
    disabled, such a miss raises a diagnostic instead of touching the network.
    """

    fetch_on_miss: bool
