from pipelex.cogt.exceptions import CogtError


class GatewayError(CogtError):
    pass


class GatewayFactoryError(GatewayError):
    pass


class GatewayCredentialsError(GatewayError):
    pass


class GatewayDeckError(GatewayError):
    pass


class GatewayExtractResponseError(GatewayError):
    pass
