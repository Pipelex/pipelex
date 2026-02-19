import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum as StrEnum
else:
    from backports.strenum import StrEnum as StrEnum
