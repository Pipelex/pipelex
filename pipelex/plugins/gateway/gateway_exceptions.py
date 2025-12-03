from pipelex.cogt.exceptions import CogtError


class PortkeyError(CogtError):
    pass


class GatewayFactoryError(PortkeyError):
    pass


class GatewayCredentialsError(PortkeyError):
    pass
