from typing import Dict

from pipelex.types import StrEnum


class TokenCategory(StrEnum):
    INPUT = "input"
    INPUT_CACHED = "input_cached"
    INPUT_NON_CACHED = "input_non_cached"
    INPUT_JOINED = "input_joined"  # joined = cached + non-cached
    INPUT_AUDIO = "input_audio"
    OUTPUT = "output"
    OUTPUT_AUDIO = "output_audio"
    OUTPUT_REASONING = "output_reasoning"
    OUTPUT_ACCEPTED_PREDICTION = "output_accepted_prediction"
    OUTPUT_REJECTED_PREDICTION = "output_rejected_prediction"


NbTokensByCategoryDict = Dict[TokenCategory, int]
TokenCostsByCategoryDict = Dict[TokenCategory, float]
