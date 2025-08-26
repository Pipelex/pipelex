import sys

print("jdsjoqdjo,", sys.version_info, sys.version_info >= (3, 11))
if sys.version_info >= (3, 11):  # real std-lib
    from enum import StrEnum
else:  # back-port
    from backports.strenum import StrEnum

__all__ = ["StrEnum"]
