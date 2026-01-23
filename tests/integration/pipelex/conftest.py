"""Integration test configuration and fixtures.

This conftest.py imports fixtures from organized modules, making them available to tests.
"""

# Import all fixtures from fixture modules
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
from .fixtures.llm_model_backend_fixtures import (
    extract_handle_from_model_backend,
    extract_model_backend,
    img_gen_handle_from_model_backend,
    img_gen_model_backend,
    llm_handle_from_model_backend,
    llm_model_backend,
)
from .fixtures.plugin_fixtures import plugin_for_anthropic, plugin_for_openai

# Make fixtures available (prevent unused import warnings)
__all__ = [
    # LLM fixtures
    "llm_job_params",
    "llm_preset_id",
    # Combined model/backend fixtures (new efficient approach)
    "llm_model_backend",
    "llm_handle_from_model_backend",
    "img_gen_model_backend",
    "img_gen_handle_from_model_backend",
    "extract_model_backend",
    "extract_handle_from_model_backend",
    # Plugin fixtures
    "plugin_for_openai",
    "plugin_for_anthropic",
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
