from pipelex.cogt.exceptions import CogtError


class GatewayError(CogtError):
    pass


class GatewayFactoryError(GatewayError):
    pass


class GatewayCredentialsError(GatewayError):
    pass


class GatewayExtractResponseError(GatewayError):
    pass


class GatewaySearchResponseError(GatewayError):
    pass


class GatewaySearchEmptyResultError(GatewayError):
    pass
