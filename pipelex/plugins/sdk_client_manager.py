from pipelex.plugins.sdk_client_registry import SdkClientRegistry


class SdkClientManager:
    def __init__(self):
        self.sdk_client_registry = SdkClientRegistry()

    def setup(self):
        pass

    def teardown(self):
        self.sdk_client_registry.teardown()
