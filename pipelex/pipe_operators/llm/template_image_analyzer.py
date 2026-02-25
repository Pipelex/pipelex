"""Backwards compatibility re-exports for template image analyzer.

These types have been moved to pipelex.pipe_operators.shared.template_image_analyzer.
This module re-exports them for backwards compatibility.
"""

# Re-export from shared module for backwards compatibility
from pipelex.pipe_operators.shared.template_image_analyzer import (
    TemplateImageAnalyzer,
    UnusedInputError,
    WithImagesFilterError,
)

__all__ = ["TemplateImageAnalyzer", "UnusedInputError", "WithImagesFilterError"]
