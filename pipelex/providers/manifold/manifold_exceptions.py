from pipelex.cogt.exceptions import CogtError


class ManifoldError(CogtError):
    pass


class ManifoldFactoryError(ManifoldError):
    pass


class ManifoldCredentialsError(ManifoldError):
    pass


class ManifoldEndpointError(ManifoldError):
    """The backend declares no usable endpoint for the Pipelex Manifold service.

    Its own error rather than a credentials one, because the remedy is a different variable and
    because there is deliberately no default to fall back on: an empty-resolving endpoint that
    silently became a vendor's public URL would carry our service token to the wrong company.
    """


class ManifoldExtractResponseError(ManifoldError):
    pass


class ManifoldSearchResponseError(ManifoldError):
    pass


class ManifoldSearchEmptyResultError(ManifoldError):
    pass
