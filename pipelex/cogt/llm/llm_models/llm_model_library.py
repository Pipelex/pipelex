import os
from typing import Any, Dict, List

from pydantic import Field, RootModel
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import LLMModelPlatformError, LLMModelProviderError
from pipelex.cogt.llm.llm_models.llm_model import LATEST_VERSION_NAME, LLMModel
from pipelex.cogt.llm.llm_models.llm_model_provider_abstract import LLMModelProviderAbstract
from pipelex.cogt.llm.llm_models.llm_platform import DEFAULT_PLATFORM_INDICATOR, LLMPlatform, LLMPlatformChoice
from pipelex.libraries.library_config import LibraryConfig
from pipelex.tools.exceptions import ToolException
from pipelex.tools.misc.toml_utils import load_toml_from_path

# Some types to clarify what dictionaries we're loading from the TOML files
LLMModelDict = Dict[str, Any]
LLMModelVersion = str
LLMModelGroup = Dict[LLMModelVersion, LLMModelDict]
LLMName = str
LLMModelFamilyGroups = Dict[LLMName, LLMModelGroup]
LLMFamilyName = str
LLMModelLibraryDict = Dict[LLMFamilyName, LLMModelFamilyGroups]


class LLMModelLibraryError(ToolException):
    pass


LLMModelLibraryRoot = List[LLMModel]


class LLMModelLibrary(LLMModelProviderAbstract, RootModel[LLMModelLibraryRoot]):
    root: LLMModelLibraryRoot = Field(default_factory=list)

    @override
    def setup(self):
        llm_model_library_dict = self.load_llm_model_library_dict()
        for llm_family, llm_family_groups in llm_model_library_dict.items():
            for llm_group_name, llm_group in llm_family_groups.items():
                for version, llm_model_dict in llm_group.items():
                    complete_llm_model_dict = {
                        **llm_model_dict,
                        "llm_family": llm_family,
                        "llm_name": llm_group_name,
                        "version": version,
                    }
                    if "default_platform" not in llm_model_dict:
                        complete_llm_model_dict["default_platform"] = list(llm_model_dict["platform_llm_id"].keys())[0]
                    llm_model = LLMModel.model_validate(complete_llm_model_dict)
                    self.root.append(llm_model)

        log.debug(f"Loaded {len(self.root)} llm models")

    @override
    def teardown(self):
        self.root = []

    @property
    @override
    def desc(self) -> str:
        return "TOML-based llm model provider with models in memory"

    @classmethod
    def load_llm_model_library_dict(cls) -> LLMModelLibraryDict:
        libraries_path = LibraryConfig.exported_llm_integrations_path
        llm_library: LLMModelLibraryDict = {}
        for library_file_name in sorted(os.listdir(libraries_path)):
            library_path = os.path.join(libraries_path, library_file_name)
            llm_families: LLMModelLibraryDict = load_toml_from_path(library_path)
            llm_library.update(llm_families)
        return llm_library

    @override
    def get_all_llm_models(self) -> List[LLMModel]:
        return self.root

    @override
    def get_llm_model(
        self,
        llm_name: str,
        llm_version: str,
        llm_platform_choice: LLMPlatformChoice,
    ) -> LLMModel:
        if llm_version == LATEST_VERSION_NAME:
            return self._get_llm_model_latest_version(llm_name=llm_name, llm_platform_choice=llm_platform_choice)

        found_llm_models = [llm_model for llm_model in self.root if llm_model.llm_name == llm_name and llm_model.version == llm_version]
        if not found_llm_models:
            raise LLMModelProviderError(f"Model '{llm_name}' version '{llm_version}' not found")
        if len(found_llm_models) > 1:
            raise LLMModelProviderError(f"Model '{llm_name}' version '{llm_version}' has multiple instances in the library")
        llm_model = found_llm_models[0]

        if isinstance(llm_platform_choice, LLMPlatform):
            llm_platform: LLMPlatform = llm_platform_choice
            if llm_platform not in llm_model.platform_llm_id:
                raise LLMModelPlatformError(f"Missing llm id for LLM model {llm_model.name_and_version}'s chosen platform='{llm_platform}'")
        return llm_model

    def _get_llm_model_latest_version(
        self,
        llm_name: str,
        llm_platform_choice: LLMPlatformChoice,
    ) -> LLMModel:
        found_llm_models = [llm_model for llm_model in self.root if llm_model.llm_name == llm_name]
        if not found_llm_models:
            raise LLMModelProviderError(f"Could not find model named '{llm_name}'")
        elif len(found_llm_models) == 1:
            # only one so it is the latest we've got
            llm_model = found_llm_models[0]
        elif chosen_model := next((model for model in found_llm_models if model.version == LATEST_VERSION_NAME), None):
            # we've got a version named 'latest' so we use it
            llm_model = chosen_model
        elif isinstance(llm_platform_choice, LLMPlatform):
            llm_platform: LLMPlatform = llm_platform_choice
            llm_models_with_platform = [model for model in found_llm_models if llm_platform in model.platform_llm_id]
            if not llm_models_with_platform:
                raise LLMModelProviderError(f"Model '{llm_name}' has no version for platform '{llm_platform}'")
            llm_model = max(llm_models_with_platform, key=lambda m: m.version)
        else:
            assert llm_platform_choice == DEFAULT_PLATFORM_INDICATOR
            llm_model = max(found_llm_models, key=lambda m: m.version)
        return llm_model
