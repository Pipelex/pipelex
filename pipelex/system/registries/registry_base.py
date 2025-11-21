from pydantic import BaseModel

ModelType = type[BaseModel]


class RegistryModels:
    @classmethod
    def get_all_models(cls) -> list[ModelType]:
        model_lists: list[list[ModelType]] = [getattr(cls, attr) for attr in dir(cls) if isinstance(getattr(cls, attr), list)]
        all_models: set[ModelType] = set()
        for model_list in model_lists:
            all_models.update(model_list)

        return list(all_models)
