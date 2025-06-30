from pipelex.cogt.llm.llm_models.llm_engine import LLMEngine
from pipelex.cogt.llm.llm_models.llm_engine_blueprint import LLMEngineBlueprint
from pipelex.cogt.llm.llm_models.llm_platform import DEFAULT_PLATFORM_INDICATOR, LLMPlatform
from pipelex.config import get_config
from pipelex.hub import get_llm_models_provider


class LLMEngineFactory:
    @classmethod
    def make_llm_engine(
        cls,
        llm_engine_blueprint: LLMEngineBlueprint,
    ) -> LLMEngine:
        """
        Create an instance of LLMEngine based on the parameters provided through the LLMEngineCard.

        Args:
            llm_engine_blueprint: LLMEngineBlueprint

        """
        llm_platform_choice = llm_engine_blueprint.llm_platform_choice
        llm_model = get_llm_models_provider().get_llm_model(
            llm_name=llm_engine_blueprint.llm_name,
            llm_version=llm_engine_blueprint.llm_version,
            llm_platform_choice=llm_platform_choice,
        )

        llm_platform: LLMPlatform
        if isinstance(llm_platform_choice, LLMPlatform):
            llm_platform = llm_platform_choice
        else:
            assert llm_platform_choice == DEFAULT_PLATFORM_INDICATOR
            llm_config = get_config().cogt.llm_config
            llm_platform = llm_config.get_preferred_platform(llm_name=llm_engine_blueprint.llm_name) or llm_model.default_platform

        return LLMEngine(
            llm_platform=llm_platform,
            llm_model=llm_model,
        )
