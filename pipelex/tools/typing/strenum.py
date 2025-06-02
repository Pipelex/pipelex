from enum import Enum


# Not natively available in Python <3.11
class StrEnum(str, Enum):
    """
    A string enum class that inherits from str and Enum.
    """
