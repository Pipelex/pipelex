from pipelex.cogt.exceptions import CogtError


class PortkeyError(CogtError):
    pass


class PortkeyFactoryError(PortkeyError):
    pass


class PortkeyCredentialsError(PortkeyError):
    pass
