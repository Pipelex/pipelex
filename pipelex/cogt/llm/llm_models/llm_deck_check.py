# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from pipelex.cogt.llm.llm_models.llm_setting import LLMSetting, LLMSettingOrPresetId
from pipelex.hub import get_llm_deck
from pipelex.tools.config.errors import LLMPresetNotFoundError


def check_llm_setting_with_config(llm_setting_or_preset_id: LLMSettingOrPresetId, is_disabled_allowed: bool = False):
    if isinstance(llm_setting_or_preset_id, LLMSetting):
        return
    preset_id: str = llm_setting_or_preset_id
    if preset_id in get_llm_deck().llm_presets:
        return
    raise LLMPresetNotFoundError(f"llm preset id '{preset_id}' not found in deck")
