# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from enum import StrEnum

BOLD_FONT = "\033[1m"
RESET_FONT = "\033[0m"


class TerminalColor(StrEnum):
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    BLUE = "\033[0;34m"
    WHITE = "\033[0;37m"
    CYAN = "\033[0;36m"
    MAGENTA = "\033[0;35m"
    YELLOW = "\033[0;33m"
