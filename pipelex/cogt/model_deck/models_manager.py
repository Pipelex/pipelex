from typing_extensions import override

from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.cogt.model_deck.models_manager_abstract import ModelsManagerAbstract
from pipelex.cogt.model_routing.routing_profile_library import RoutingProfileLibrary


class ModelsManager(ModelsManagerAbstract):
    def __init__(self) -> None:
        self.routing_profile_library = RoutingProfileLibrary.make_empty()
        self.inference_backend_library = InferenceBackendLibrary.make_empty()

    @override
    def teardown(self) -> None:
        self.routing_profile_library.reset()
        self.inference_backend_library.reset()

    @override
    def setup(self) -> None:
        self.routing_profile_library.load()
        self.inference_backend_library.load()
