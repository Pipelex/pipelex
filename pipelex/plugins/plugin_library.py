# import os
# from typing import Any, Dict, List

# from pydantic import Field, RootModel
# from typing_extensions import override

# from pipelex import log
# from pipelex.libraries.library_config import LibraryConfig
# from pipelex.tools.exceptions import ToolException
# from pipelex.tools.misc.toml_utils import load_toml_from_path

# LLMPluginLibraryRoot = List[LLMModel]


# class LLMModelLibrary(RootModel[LLMPluginLibraryRoot]):
#     root: LLMPluginLibraryRoot = Field(default_factory=list)

#     @override
#     def setup(self):
#         log.debug(f"Loaded {len(self.root)} llm platforms")

#     @override
#     def teardown(self):
#         self.root = []

#     @property
#     @override
#     def desc(self) -> str:
#         return "TOML-based llm model provider with models in memory"

#     @classmethod
#     def load_llm_model_library_dict(cls) -> LLMModelLibraryDict:
#         libraries_path = LibraryConfig.exported_llm_integrations_path
#         if not os.path.exists(libraries_path):
#             raise LLMModelLibraryError(f"LLM model library path `{libraries_path}` not found. Please run `pipelex init-libraries` to create it.")
#         llm_library: LLMModelLibraryDict = {}
#         for library_file_name in sorted(os.listdir(libraries_path)):
#             library_path = os.path.join(libraries_path, library_file_name)
#             llm_families: LLMModelLibraryDict = load_toml_from_path(library_path)
#             llm_library.update(llm_families)
#         return llm_library

#     @override
#     def get_all_llm_models(self) -> List[LLMModel]:
#         return self.root

#     @override
#     def get_llm_model(
#         self,
#         llm_name: str,
#         llm_version: str,
#         llm_platform_choice: LLMPlatformChoice,
#     ) -> LLMModel:
#         return llm_model
