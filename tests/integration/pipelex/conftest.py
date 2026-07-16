"""Integration test configuration and fixtures.

This conftest.py imports fixtures from organized modules, making them available to tests.
"""

# Import all fixtures from fixture modules
from .fixtures.combo_fixtures import (
    extract_combo,
    img_gen_combo,
    llm_combo,
    search_combo,
)
from .fixtures.extract_fixtures import (
    extract_choice_for_image,
    extract_choice_for_pdf,
    extract_handle_from_image,
    extract_handle_from_pdf,
    extract_job_params,
)
from .fixtures.generator_fixtures import content_generator, generated_content_factory
from .fixtures.img_gen_fixtures import img_gen_job_params
from .fixtures.llm_fixtures import llm_job_params, llm_preset_id
from .fixtures.model_combo import ModelCombo
from .fixtures.model_handle_fixtures import model_handle_for_anthropic, model_handle_for_openai

# Make fixtures available (prevent unused import warnings)
__all__ = [
    # Model combo type
    "ModelCombo",
    # LLM fixtures
    "llm_job_params",
    "llm_preset_id",
    # Combined model/backend fixtures (efficient approach with NamedTuple)
    "llm_combo",
    "img_gen_combo",
    "extract_combo",
    "search_combo",
    # Model handle fixtures
    "model_handle_for_openai",
    "model_handle_for_anthropic",
    # Image generation fixtures
    "img_gen_job_params",
    # Generator fixtures
    "generated_content_factory",
    "content_generator",
    # Extract fixtures
    "extract_handle_from_image",
    "extract_handle_from_pdf",
    "extract_choice_for_pdf",
    "extract_choice_for_image",
    "extract_job_params",
]
