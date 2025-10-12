"""Test case constants and data definitions.

This package contains pure-Python test-case definitions without test logic.
Each module exposes only data constants that can be imported cleanly.
"""

from tests.cases.documents import PDFTestCases
from tests.cases.images import ImageTestCases
from tests.cases.jinja2_templates import JINJA2TestCases
from tests.cases.registry import ClassRegistryTestCases, FileHelperTestCases, Fruit
from tests.cases.urls import TestURLs

__all__ = [
    "ClassRegistryTestCases",
    "FileHelperTestCases",
    "Fruit",
    "ImageTestCases",
    "JINJA2TestCases",
    "PDFTestCases",
    "TestURLs",
]
