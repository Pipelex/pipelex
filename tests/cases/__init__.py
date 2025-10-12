"""Test case constants and data definitions.

This package contains pure-Python test-case definitions without test logic.
Each module exposes only data constants that can be imported cleanly.
"""

from .documents import PDFTestCases
from .images import ImageTestCases
from .jinja2_templates import JINJA2TestCases
from .registry import ClassRegistryTestCases, FileHelperTestCases, Fruit
from .urls import TestURLs

__all__ = [
    "ClassRegistryTestCases",
    "FileHelperTestCases",
    "Fruit",
    "ImageTestCases",
    "JINJA2TestCases",
    "PDFTestCases",
    "TestURLs",
]
