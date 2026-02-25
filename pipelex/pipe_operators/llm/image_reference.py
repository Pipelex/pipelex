"""Backwards compatibility re-exports for image reference types.

These types have been moved to pipelex.pipe_operators.shared.image_reference.
This module re-exports them for backwards compatibility.
"""

# Re-export from shared module for backwards compatibility
from pipelex.pipe_operators.shared.image_reference import ImageReference, ImageReferenceKind

__all__ = ["ImageReference", "ImageReferenceKind"]
